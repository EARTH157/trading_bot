import json

from core.agents.sentiment_analyst import SentimentAnalystAgent


def test_missing_news_is_neutral_not_bullish(tmp_path):
    agent = SentimentAnalystAgent()
    md = tmp_path / "AAPL.md"
    md.write_text("# รายงานข่าว\n_ไม่พบข่าวล่าสุด_", encoding="utf-8")

    import asyncio
    result = asyncio.run(agent.run({"news_files": {"AAPL": str(md)}, "article_counts": {"AAPL": 0}}))

    sent = result.data["sentiment_analysis"]["AAPL"]
    assert sent["score"] == 0.0
    assert sent["label"] == "NEUTRAL"


def test_validate_llm_entry_clamps_and_relabels():
    entry = SentimentAnalystAgent._validate_llm_entry({"score": 5, "label": "BEARISH", "catalysts": "x"})
    assert entry["score"] == 1.0
    assert entry["label"] == "BULLISH"  # label มาจาก score เสมอ
    assert entry["catalysts"] == []


def test_validate_llm_entry_rejects_bad_scores():
    assert SentimentAnalystAgent._validate_llm_entry({"score": "very bullish"}) is None
    assert SentimentAnalystAgent._validate_llm_entry({"score": float("nan")}) is None
    assert SentimentAnalystAgent._validate_llm_entry({"label": "BULLISH"}) is None
    assert SentimentAnalystAgent._validate_llm_entry("BULLISH") is None


async def test_llm_output_limited_to_requested_symbols(monkeypatch):
    agent = SentimentAnalystAgent()

    async def fake_llm(prompt, system_instruction=None, json_output=False):
        return json.dumps({
            "aapl": {"score": 0.4},
            "GME": {"score": 1.0},          # ไม่ได้ร้องขอ -> ต้องถูกทิ้ง
            "MSFT": {"score": "oops"},      # ไม่ผ่านการตรวจสอบ -> ต้องถูกทิ้ง
        })

    monkeypatch.setattr(agent, "call_llm", fake_llm)
    result = await agent._batch_analyze_with_gemini({"AAPL": "news", "MSFT": "news"})

    assert set(result) == {"AAPL"}
    assert result["AAPL"]["score"] == 0.4
