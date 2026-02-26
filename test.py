#!/usr/bin/env python3
"""
qGPU Demo — Unified Test & Chat CLI

Usage:
  python test.py quick          Run a few prompts, show routing decisions
  python test.py full           Run all prompts with detailed output
  python test.py csv            Run all prompts, save results to CSV
  python test.py chat           Interactive chat with the router agent
  python test.py ecommerce      Interactive e-commerce demo (router + specialist)
  python test.py health         Check health of all services
"""

import argparse
import asyncio
import aiohttp
import csv
import json
import os
import sys
import time
from datetime import datetime


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NODE_IP = os.getenv("NODE_IP", "127.0.0.1")
ROUTER_URL = os.getenv("ROUTER_URL", f"http://{NODE_IP}:30090/v1/chat/completions")
SIMPLE_URL = os.getenv("SIMPLE_URL", f"http://{NODE_IP}:30081/v1/chat/completions")
SPECIALIST_URL = os.getenv("SPECIALIST_URL", f"http://{NODE_IP}:30082/v1/chat/completions")

SIMPLE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
SPECIALIST_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

QUICK_PROMPTS = [
    "What is 2+2?",
    "Hello, how are you?",
    "Explain quantum computing in detail, including qubits and superposition.",
    "Write a haiku about clouds.",
    "Compare REST vs GraphQL APIs with examples.",
]

FULL_PROMPTS = QUICK_PROMPTS + [
    "What's the weather like today?",
    "Who won the World Cup in 2022?",
    "Compare microservices vs monolithic architecture.",
    "Explain the theory of relativity with mathematical equations.",
    "What is Kubernetes?",
    "What are the latest developments in AI?",
    "Search for information about quantum computing breakthroughs in 2024.",
    "What's the stock price of Apple today?",
    "What's happening in the tech industry right now?",
]

ECOMMERCE_SYSTEM_ROUTER = """You are a smart e-commerce routing agent for TechShop, an online electronics store.

Your job: decide if you can handle the customer query yourself, or if it needs the product specialist.

HANDLE YOURSELF (reply directly):
- Greetings, thanks, goodbyes
- Store hours, shipping policy, return policy
- Order status checks
- Simple yes/no questions

ROUTE TO SPECIALIST (reply with EXACTLY "ROUTE:" followed by a brief reason):
- Product recommendations or comparisons
- Technical specifications
- Complex product questions
- Purchase advice

Store info you know:
- Free shipping on orders over $50
- 30-day return policy
- Store hours: 9am-9pm EST, 7 days a week
- Support email: help@techshop.com"""

ECOMMERCE_SYSTEM_SPECIALIST = """You are a product specialist at TechShop, an online electronics store.

You provide detailed, knowledgeable answers about electronics products. You know about:
- Laptops, desktops, tablets
- Smartphones and accessories
- Audio equipment (headphones, speakers)
- Smart home devices
- Gaming hardware

Be helpful, specific, and recommend products with approximate prices.
Keep answers concise but informative (3-5 sentences max)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

C_RESET = "\033[0m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_DIM = "\033[90m"
C_BOLD = "\033[1m"
C_RED = "\033[31m"


async def call_router(session, prompt, max_tokens=300):
    """Send prompt to the router agent service and return result dict."""
    payload = {"messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    start = time.time()
    try:
        async with session.post(ROUTER_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            elapsed = time.time() - start
            if resp.status != 200:
                error_text = await resp.text()
                return {"prompt": prompt, "response": f"ERROR: {resp.status}", "action": "error",
                        "reason": error_text[:200], "source": "error", "elapsed": elapsed,
                        "tokens": 0, "status": "error"}
            data = await resp.json()
            meta = data.get("routing_metadata", {})
            choices = data.get("choices", [])
            text = choices[0]["message"]["content"] if choices else ""
            usage = data.get("usage", {})
            return {"prompt": prompt, "response": text, "action": meta.get("action", "unknown"),
                    "reason": meta.get("reason", "unknown"), "source": meta.get("source", "unknown"),
                    "elapsed": elapsed, "tokens": usage.get("total_tokens", 0),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "status": "success"}
    except asyncio.TimeoutError:
        return {"prompt": prompt, "response": "ERROR: timeout", "action": "timeout",
                "reason": "60s timeout", "source": "error", "elapsed": 60.0,
                "tokens": 0, "status": "timeout"}
    except Exception as e:
        return {"prompt": prompt, "response": f"ERROR: {e}", "action": "error",
                "reason": str(e), "source": "error", "elapsed": time.time() - start,
                "tokens": 0, "status": "error"}


async def call_direct(session, url, model, messages, max_tokens=200):
    """Call a vLLM endpoint directly."""
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7}
    start = time.time()
    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        data = await resp.json()
    elapsed = time.time() - start
    text = data["choices"][0]["message"]["content"].strip()
    tokens = data["usage"]["completion_tokens"]
    return text, elapsed, tokens


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def cmd_health():
    """Check health of all services."""
    endpoints = {
        "Router Agent (:30090)": ROUTER_URL.replace("/v1/chat/completions", "/health"),
        "Simple Agent  (:30081)": SIMPLE_URL.replace("/v1/chat/completions", "/health"),
        "Specialist    (:30082)": SPECIALIST_URL.replace("/v1/chat/completions", "/health"),
    }
    async with aiohttp.ClientSession() as session:
        for name, url in endpoints.items():
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        print(f"  {C_GREEN}OK{C_RESET}  {name}")
                    else:
                        print(f"  {C_RED}ERR{C_RESET} {name} — HTTP {resp.status}")
            except Exception as e:
                print(f"  {C_RED}ERR{C_RESET} {name} — {e}")


async def cmd_test(prompts, verbose=True):
    """Run prompts through the router and print results."""
    print(f"\n{C_BOLD}Router URL:{C_RESET} {ROUTER_URL}")
    print(f"{C_BOLD}Prompts:{C_RESET}    {len(prompts)}\n")

    async with aiohttp.ClientSession() as session:
        tasks = [call_router(session, p) for p in prompts]
        results = await asyncio.gather(*tasks)

    for i, r in enumerate(results, 1):
        ok = r["status"] == "success"
        icon = f"{C_GREEN}OK{C_RESET}" if ok else f"{C_RED}ERR{C_RESET}"
        print(f"  {icon} {i:>2}. {r['prompt'][:55]}")
        print(f"       {C_DIM}→ {r['action']} | {r['source']} | {r['elapsed']:.2f}s{C_RESET}")
        if verbose and ok:
            print(f"       {C_DIM}  {r['reason']}{C_RESET}")
            print(f"       {C_DIM}  {r['response'][:120]}...{C_RESET}")
        print()

    # Summary
    actions = {}
    for r in results:
        a = r["action"]
        actions[a] = actions.get(a, 0) + 1

    print(f"{C_BOLD}Routing distribution:{C_RESET}")
    for a, c in sorted(actions.items()):
        print(f"  {a}: {c}")

    total_time = sum(r["elapsed"] for r in results)
    total_tok = sum(r["tokens"] for r in results)
    ok_count = sum(1 for r in results if r["status"] == "success")
    print(f"\n  {ok_count}/{len(results)} succeeded | {total_tok} tokens | {total_time:.2f}s total\n")
    return results


async def cmd_csv(prompts):
    """Run prompts and write results to a timestamped CSV."""
    results = await cmd_test(prompts, verbose=False)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = f"router_test_{ts}.csv"

    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "test_id", "timestamp", "prompt", "response",
            "routing_action", "routing_reason", "source",
            "elapsed_seconds", "total_tokens", "status",
        ])
        writer.writeheader()
        for i, r in enumerate(results, 1):
            writer.writerow({
                "test_id": i,
                "timestamp": datetime.now().isoformat(),
                "prompt": r["prompt"],
                "response": r["response"],
                "routing_action": r["action"],
                "routing_reason": r["reason"],
                "source": r["source"],
                "elapsed_seconds": f"{r['elapsed']:.3f}",
                "total_tokens": r["tokens"],
                "status": r["status"],
            })

    print(f"  Saved to: {csv_file}\n")


async def cmd_chat():
    """Interactive chat through the router agent."""
    print(f"\n{C_BOLD}{'=' * 55}{C_RESET}")
    print(f"{C_BOLD}  qGPU Router Chat{C_RESET}")
    print(f"  Router: {ROUTER_URL}")
    print(f"{C_BOLD}{'=' * 55}{C_RESET}")
    print(f"  Type a message (or 'quit' to exit)\n")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                query = input(f"  {C_BOLD}You:{C_RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n\n  Goodbye!\n")
                break

            if not query:
                continue
            if query.lower() in ("quit", "exit", "q"):
                print(f"\n  Goodbye!\n")
                break

            r = await call_router(session, query)
            if r["status"] != "success":
                print(f"\n  {C_RED}Error:{C_RESET} {r['response']}\n")
                continue

            print(f"\n  {C_DIM}[{r['action']} → {r['source']} | {r['elapsed']:.2f}s]{C_RESET}")
            print(f"  {r['response']}\n")


async def cmd_ecommerce():
    """Interactive e-commerce demo with routing log."""
    print(f"\n{C_BOLD}{'=' * 55}{C_RESET}")
    print(f"{C_BOLD}  TechShop AI Assistant{C_RESET}")
    print(f"  Powered by 2 models on 1 GPU (qGPU)")
    print(f"  Router:     {SIMPLE_MODEL} (:30081)")
    print(f"  Specialist: {SPECIALIST_MODEL} (:30082)")
    print(f"{C_BOLD}{'=' * 55}{C_RESET}")
    print(f"  Type your question (or 'quit' to exit)\n")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                query = input(f"  {C_BOLD}You:{C_RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n\n  Goodbye!\n")
                break

            if not query:
                continue
            if query.lower() in ("quit", "exit", "q"):
                print(f"\n  Goodbye!\n")
                break

            print()

            # Step 1: Router decides
            msgs_router = [
                {"role": "system", "content": ECOMMERCE_SYSTEM_ROUTER},
                {"role": "user", "content": query},
            ]
            router_reply, router_time, router_tokens = await call_direct(
                session, SIMPLE_URL, SIMPLE_MODEL, msgs_router
            )

            if router_reply.startswith("ROUTE:"):
                reason = router_reply[6:].strip()
                print(f"  {C_YELLOW}[Router → Specialist]{C_RESET} {reason} ({router_time:.2f}s)")

                msgs_spec = [
                    {"role": "system", "content": ECOMMERCE_SYSTEM_SPECIALIST},
                    {"role": "user", "content": query},
                ]
                spec_reply, spec_time, spec_tokens = await call_direct(
                    session, SPECIALIST_URL, SPECIALIST_MODEL, msgs_spec
                )
                total = router_time + spec_time
                print(f"  {C_CYAN}[Specialist]{C_RESET} ({spec_time:.2f}s, {spec_tokens} tok)\n")
                print(f"  {spec_reply}\n")
                print(f"  {C_DIM}Total: {total:.2f}s | Router: {router_tokens} tok | Specialist: {spec_tokens} tok{C_RESET}\n")
            else:
                print(f"  {C_GREEN}[Router handled]{C_RESET} ({router_time:.2f}s, {router_tokens} tok)\n")
                print(f"  {router_reply}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="qGPU Demo — Test & Chat CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  health       Check health of all services
  quick        Run 5 prompts through router (default)
  full         Run 15 prompts through router
  csv          Run all prompts and save results to CSV
  chat         Interactive chat via router agent service
  ecommerce    Interactive e-commerce demo (router + specialist)

environment:
  NODE_IP      Node IP address (default: 127.0.0.1)
  ROUTER_URL   Router endpoint override
  SIMPLE_URL   Simple agent endpoint override
  SPECIALIST_URL  Specialist agent endpoint override
""",
    )
    parser.add_argument("command", nargs="?", default="quick",
                        choices=["health", "quick", "full", "csv", "chat", "ecommerce"],
                        help="Command to run (default: quick)")

    args = parser.parse_args()

    print(f"\n{C_BOLD}qGPU Demo Test CLI{C_RESET}")
    print(f"{'─' * 40}")

    if args.command == "health":
        asyncio.run(cmd_health())
    elif args.command == "quick":
        asyncio.run(cmd_test(QUICK_PROMPTS))
    elif args.command == "full":
        asyncio.run(cmd_test(FULL_PROMPTS))
    elif args.command == "csv":
        asyncio.run(cmd_csv(FULL_PROMPTS))
    elif args.command == "chat":
        asyncio.run(cmd_chat())
    elif args.command == "ecommerce":
        asyncio.run(cmd_ecommerce())


if __name__ == "__main__":
    main()
