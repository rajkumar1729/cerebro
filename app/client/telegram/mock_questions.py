"""Separate mock test dataset for Telegram active-recall quizzes.

This file provides standalone test questions (MCQ, MSQ, SEQ) categorized by topics.
Once live database/LLM question generation is wired, this module can be removed.
"""
from __future__ import annotations

from typing import Dict, List, Any
from app.model.question import MCQ, MSQ, SEQ, QuestionType

MOCK_TOPICS: Dict[str, Dict[str, str]] = {
    "science": {
        "title": "🔬 Science & Technology",
        "description": "System Design, Data Structures & Cloud Computing",
    },
    "business": {
        "title": "📈 Business & Finance",
        "description": "Corporate Finance, Metrics & Valuation",
    },
    "trivia": {
        "title": "💡 General Knowledge & Trivia",
        "description": "Science, Physics & Astronomy Trivia",
    },
}

MOCK_QUESTION_SETS: Dict[str, List[QuestionType]] = {
    "science": [
        MCQ(
            question="What is the primary function of a Load Balancer in system design?",
            options=[
                "Distribute incoming network traffic across multiple servers",
                "Encrypt and securely store database passwords",
                "Compile high-level source code into binary files",
                "Cache static HTML content on the client side browser",
            ],
            answer="Distribute incoming network traffic across multiple servers",
            explanation="A load balancer acts as a reverse proxy to distribute incoming application traffic across multiple backend servers to ensure high availability and reliability.",
        ),
        MSQ(
            question="Which of the following are core ACID properties guaranteed by Relational Database Management Systems (RDBMS)? (Select all that apply)",
            options=[
                "Atomicity",
                "Consistency",
                "Isolation",
                "Availability",
            ],
            answer=["Atomicity", "Consistency", "Isolation"],
            explanation="ACID stands for Atomicity, Consistency, Isolation, and Durability. Availability is part of the CAP theorem.",
        ),
        SEQ(
            question="Explain the primary difference between TCP and UDP networking protocols.",
            answer="TCP is connection-oriented and reliable with error recovery and packet ordering. UDP is connectionless, fast, and does not guarantee packet delivery or order.",
            explanation="TCP uses handshakes to guarantee data delivery in order (ideal for web/email). UDP sacrifices reliability for lower latency (ideal for video streaming/gaming).",
        ),
    ],
    "business": [
        MCQ(
            question="What does ROI stand for in financial performance measurement?",
            options=[
                "Return on Investment",
                "Rate of Inflation",
                "Risk of Insolvency",
                "Revenue over Interest",
            ],
            answer="Return on Investment",
            explanation="Return on Investment (ROI) evaluates the efficiency or profitability of an investment relative to its cost.",
        ),
        MSQ(
            question="Which of the following financial statements are standard components of corporate reporting? (Select all that apply)",
            options=[
                "Balance Sheet",
                "Income Statement",
                "Cash Flow Statement",
                "Customer Satisfaction Survey",
            ],
            answer=["Balance Sheet", "Income Statement", "Cash Flow Statement"],
            explanation="The core financial statements are Balance Sheet, Income Statement, and Cash Flow Statement. Customer Satisfaction is an operational metric.",
        ),
        SEQ(
            question="What is EBITDA and why do investors use it to evaluate companies?",
            answer="EBITDA stands for Earnings Before Interest, Taxes, Depreciation, and Amortization. It measures pure operating profitability excluding financing and accounting choices.",
            explanation="By removing interest rate, tax, and non-cash depreciation differences, EBITDA provides a standardized view of operating cash flow across different companies.",
        ),
    ],
    "trivia": [
        MCQ(
            question="Which chemical element is represented by the symbol 'O' on the periodic table?",
            options=[
                "Oxygen",
                "Osmium",
                "Gold",
                "Oganesson",
            ],
            answer="Oxygen",
            explanation="Oxygen has the symbol O and atomic number 8.",
        ),
        MSQ(
            question="Which of the following planets in our solar system are classified as Gas Giants? (Select all that apply)",
            options=[
                "Jupiter",
                "Saturn",
                "Mars",
                "Venus",
            ],
            answer=["Jupiter", "Saturn"],
            explanation="Jupiter and Saturn are the Gas Giants. Uranus and Neptune are Ice Giants, while Mars and Venus are terrestrial rocky planets.",
        ),
        SEQ(
            question="What causes the natural light display known as Aurora Borealis (Northern Lights)?",
            answer="Solar wind charged particles colliding with Earth's atmospheric gas molecules guided by the magnetic field.",
            explanation="Electrons and protons from the Sun interact with oxygen and nitrogen in Earth's upper atmosphere, causing energy emissions in brilliant lights.",
        ),
    ],
}


def get_mock_topics() -> Dict[str, Dict[str, str]]:
    """Fetch available review topics."""
    return MOCK_TOPICS


def get_mock_questions(topic_id: str) -> List[QuestionType]:
    """Fetch test questions for a given topic ID with prefix fallback handling."""
    if topic_id in MOCK_QUESTION_SETS:
        return MOCK_QUESTION_SETS[topic_id]

    # Fallback if "topic_science" or "science" is passed
    clean_id = topic_id.removeprefix("topic_")
    if clean_id in MOCK_QUESTION_SETS:
        return MOCK_QUESTION_SETS[clean_id]

    return MOCK_QUESTION_SETS.get(f"topic_{topic_id}", [])
