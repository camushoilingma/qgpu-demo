#!/usr/bin/env python3
"""Test both vLLM models simultaneously to demonstrate qGPU sharing."""

import asyncio
import aiohttp
import os
import time
import json

NODE_IP = os.getenv("NODE_IP", "127.0.0.1")
MODELS = [
    {"name": "Qwen2.5-0.5B", "url": f"http://{NODE_IP}:30081/v1/chat/completions", "model": "Qwen/Qwen2.5-0.5B-Instruct"},
    {"name": "Qwen2.5-1.5B", "url": f"http://{NODE_IP}:30082/v1/chat/completions", "model": "Qwen/Qwen2.5-1.5B-Instruct"},
]

PROMPTS = [
    "Explain what a GPU is in 2 sentences.",
    "Write a haiku about cloud computing.",
    "What is Kubernetes? One sentence.",
]


async def call_model(session, model, prompt):
    payload = {
        "model": model["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 100,
    }
    start = time.time()
    async with session.post(model["url"], json=payload) as resp:
        data = await resp.json()
    elapsed = time.time() - start
    text = data["choices"][0]["message"]["content"].strip()
    tokens = data["usage"]["completion_tokens"]
    return model["name"], prompt[:40], text, elapsed, tokens


async def main():
    print("=" * 70)
    print("qGPU Demo — Two models on ONE GPU, called simultaneously")
    print("=" * 70)

    async with aiohttp.ClientSession() as session:
        # Round 1: same prompt to both models at the same time
        print("\n--- Round 1: Same prompt, both models at once ---\n")
        prompt = "What is GPU sharing? One sentence."
        tasks = [call_model(session, m, prompt) for m in MODELS]
        results = await asyncio.gather(*tasks)
        for name, _, text, elapsed, tokens in results:
            print(f"  [{name}] ({elapsed:.2f}s, {tokens} tokens)")
            print(f"    {text}\n")

        # Round 2: different prompts, all fired concurrently
        print("--- Round 2: 3 prompts × 2 models = 6 calls at once ---\n")
        tasks = []
        for prompt in PROMPTS:
            for model in MODELS:
                tasks.append(call_model(session, model, prompt))

        start = time.time()
        results = await asyncio.gather(*tasks)
        total = time.time() - start

        for name, prompt_snip, text, elapsed, tokens in results:
            print(f"  [{name}] \"{prompt_snip}\" ({elapsed:.2f}s, {tokens} tok)")
            print(f"    {text}\n")

        print(f"--- All 6 calls completed in {total:.2f}s ---\n")

        # Round 3: throughput test — 10 concurrent requests per model
        print("--- Round 3: 10 concurrent requests per model ---\n")
        prompt = "Count from 1 to 10."
        tasks = []
        for _ in range(10):
            for model in MODELS:
                tasks.append(call_model(session, model, prompt))

        start = time.time()
        results = await asyncio.gather(*tasks)
        total = time.time() - start

        totals = {}
        for name, _, _, elapsed, tokens in results:
            if name not in totals:
                totals[name] = {"count": 0, "tokens": 0, "max_latency": 0}
            totals[name]["count"] += 1
            totals[name]["tokens"] += tokens
            totals[name]["max_latency"] = max(totals[name]["max_latency"], elapsed)

        for name, stats in totals.items():
            tps = stats["tokens"] / total
            print(f"  [{name}] {stats['count']} requests, {stats['tokens']} tokens, {tps:.1f} tok/s, max latency {stats['max_latency']:.2f}s")

        print(f"\n  Total wall time: {total:.2f}s")
        print(f"  Total requests:  {len(results)}")
        print(f"  Total tokens:    {sum(s['tokens'] for s in totals.values())}")


if __name__ == "__main__":
    asyncio.run(main())
