#!/usr/bin/env python3
"""
Router Agent Service - LLM-powered routing agent that can:
1. Route to Simple Agent (Qwen2.5-0.5B)
2. Route to Specialist Agent (Qwen2.5-1.5B)
3. Answer itself using its own LLM
4. Route to Gemini API
"""

import os
import json
import asyncio
import time
import aiohttp
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Router Agent Service")

# Configuration from environment
ROUTER_MODEL_URL = os.getenv("ROUTER_MODEL_URL", "http://vllm-half-a:8000/v1/chat/completions")
SIMPLE_AGENT_URL = os.getenv("SIMPLE_AGENT_URL", "http://vllm-half-a:8000/v1/chat/completions")
SPECIALIST_AGENT_URL = os.getenv("SPECIALIST_AGENT_URL", "http://vllm-half-b:8000/v1/chat/completions")
# Gemini API configuration - can be set via environment or secret
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_SECRET_NAME = os.getenv("GEMINI_SECRET_NAME", "gemini-api-key")
GEMINI_SECRET_KEY = os.getenv("GEMINI_SECRET_KEY", "api-key")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"

# Router model configuration
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")


class ChatRequest(BaseModel):
    messages: list
    model: Optional[str] = None
    max_tokens: Optional[int] = 200
    temperature: Optional[float] = 0.7


class RoutingDecision(BaseModel):
    action: Literal["route_simple", "route_specialist", "answer_self", "route_gemini"]
    reason: str
    confidence: Optional[float] = None


async def call_llm(session: aiohttp.ClientSession, url: str, messages: list, model: str, max_tokens: int = 200):
    """Call an LLM endpoint"""
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7
    }
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise HTTPException(status_code=resp.status, detail=f"LLM call failed: {error_text}")
            data = await resp.json()
            return data["choices"][0]["message"]["content"]
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="LLM call timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM call error: {str(e)}")


async def call_gemini(session: aiohttp.ClientSession, prompt: str):
    """Call Google Gemini API. Returns (response_text, True) on success, (None, False) on failure."""
    if not GEMINI_API_KEY:
        logger.warning("Gemini API key not configured, will fallback")
        return None, False

    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.warning(f"Gemini API returned {resp.status}: {error_text}, will fallback")
                return None, False
            data = await resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"], True
    except Exception as e:
        logger.warning(f"Gemini API error: {e}, will fallback")
        return None, False


async def router_agent_decision(session: aiohttp.ClientSession, user_message: str) -> RoutingDecision:
    """
    Use LLM to make routing decision.
    The router agent analyzes the prompt and decides where to route it.
    """
    routing_prompt = f"""You are a smart router agent. Analyze the user's request and decide the best action:

User request: "{user_message}"

Available actions:
1. "route_simple" - Route to Simple Agent (Qwen2.5-0.5B) for quick, simple queries
2. "route_specialist" - Route to Specialist Agent (Qwen2.5-1.5B) for complex, detailed responses
3. "answer_self" - Answer directly yourself if you can handle it well
4. "route_gemini" - Route to Gemini for questions requiring Google's knowledge or specific capabilities

Respond ONLY with a JSON object in this exact format:
{{
    "action": "route_simple|route_specialist|answer_self|route_gemini",
    "reason": "brief explanation of why you chose this action"
}}

JSON response:"""

    messages = [
        {"role": "system", "content": "You are a routing agent. Always respond with valid JSON only."},
        {"role": "user", "content": routing_prompt}
    ]
    
    try:
        response_text = await call_llm(session, ROUTER_MODEL_URL, messages, ROUTER_MODEL, max_tokens=150)
        
        # Extract JSON from response (handle cases where LLM adds extra text)
        response_text = response_text.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        elif "{" in response_text:
            response_text = response_text[response_text.index("{"):]
            if "}" in response_text:
                response_text = response_text[:response_text.rindex("}")+1]
        
        decision = json.loads(response_text)
        
        # Validate action
        valid_actions = ["route_simple", "route_specialist", "answer_self", "route_gemini"]
        if decision.get("action") not in valid_actions:
            logger.warning(f"Invalid action {decision.get('action')}, defaulting to route_simple")
            decision["action"] = "route_simple"
        
        return RoutingDecision(**decision)
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse routing decision: {e}, response: {response_text}")
        # Default fallback
        return RoutingDecision(
            action="route_simple",
            reason="Failed to parse routing decision, defaulting to simple agent"
        )
    except Exception as e:
        logger.error(f"Routing decision error: {e}")
        return RoutingDecision(
            action="route_simple",
            reason=f"Error in routing: {str(e)}, defaulting to simple agent"
        )


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """Main chat endpoint - router agent decides where to route"""
    async with aiohttp.ClientSession() as session:
        # Get user message
        user_message = request.messages[-1]["content"] if request.messages else ""
        
        if not user_message:
            raise HTTPException(status_code=400, detail="No message content provided")
        
        # Router agent makes decision
        logger.info(f"Router analyzing request: {user_message[:50]}...")
        decision = await router_agent_decision(session, user_message)
        logger.info(f"Router decision: {decision.action} - {decision.reason}")
        
        # Execute routing decision
        if decision.action == "route_simple":
            logger.info("Routing to Simple Agent")
            response_text = await call_llm(session, SIMPLE_AGENT_URL, request.messages, 
                                         "Qwen/Qwen2.5-0.5B-Instruct", request.max_tokens)
            source = "simple_agent"
            
        elif decision.action == "route_specialist":
            logger.info("Routing to Specialist Agent")
            response_text = await call_llm(session, SPECIALIST_AGENT_URL, request.messages,
                                         "Qwen/Qwen2.5-1.5B-Instruct", request.max_tokens)
            source = "specialist_agent"
            
        elif decision.action == "answer_self":
            logger.info("Router answering directly")
            response_text = await call_llm(session, ROUTER_MODEL_URL, request.messages,
                                         ROUTER_MODEL, request.max_tokens)
            source = "router_agent"
            
        elif decision.action == "route_gemini":
            logger.info("Routing to Gemini")
            gemini_text, gemini_ok = await call_gemini(session, user_message)
            if gemini_ok:
                response_text = gemini_text
                source = "gemini"
            else:
                logger.info("Gemini unavailable, falling back to Specialist Agent")
                response_text = await call_llm(session, SPECIALIST_AGENT_URL, request.messages,
                                             "Qwen/Qwen2.5-1.5B-Instruct", request.max_tokens)
                source = "specialist_agent (gemini_fallback)"

        else:
            # Fallback
            response_text = await call_llm(session, SIMPLE_AGENT_URL, request.messages,
                                         "Qwen/Qwen2.5-0.5B-Instruct", request.max_tokens)
            source = "simple_agent"
        
        # Return OpenAI-compatible response
        return {
            "id": f"chatcmpl-router-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model or "router-agent",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(user_message.split()),
                "completion_tokens": len(response_text.split()),
                "total_tokens": len(user_message.split()) + len(response_text.split())
            },
            "routing_metadata": {
                "action": decision.action,
                "reason": decision.reason,
                "source": source
            }
        }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "router-agent"}


@app.get("/routing/stats")
async def routing_stats():
    """Get routing statistics (placeholder for future implementation)"""
    return {"message": "Routing stats endpoint - to be implemented"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
