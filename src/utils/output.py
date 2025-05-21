import os
import smtplib
from email.mime.text import MIMEText
from .analysts import ANALYST_ORDER
import json
import requests


def sort_agent_signals(signals):
    analyst_order = {display: idx for idx, (display, _) in enumerate(ANALYST_ORDER)}
    analyst_order["Risk Management"] = len(ANALYST_ORDER)
    return sorted(signals, key=lambda x: analyst_order.get(x[0], 999))


def format_trading_output_as_text(result: dict) -> str:
    html = ["<html><body style='font-family:Arial, sans-serif;'>"]

    # Optional intro based on run parameters
    run_params = result.get("run_parameters", {})
    start = run_params.get("start_date")
    end = run_params.get("end_date")
    if start and end:
        html.append(f"<p><b>📊 This report is generated based on data from {start} to {end}.</b></p>")

    decisions = result.get("decisions")
    if not decisions:
        return "<p>No trading decisions available.</p>"

    for ticker, decision in decisions.items():
        html.append(f"<h2>📌 Analysis for {ticker}</h2>")

        table_data = []
        for agent, signals in result.get("analyst_signals", {}).items():
            if ticker not in signals:
                continue
            if agent == "risk_management_agent":
                continue

            signal = signals[ticker]
            agent_name = agent.replace("_agent", "").replace("_", " ").title()
            signal_type = signal.get("signal", "").upper()
            confidence = signal.get("confidence", 0)

            reasoning = signal.get("reasoning", "")
            if isinstance(reasoning, dict):
                reasoning = json.dumps(reasoning, indent=2)
            else:
                reasoning = str(reasoning)

            table_data.append([agent_name, signal_type, f"{confidence}%", reasoning])

        table_data = sort_agent_signals(table_data)

        html.append("<h3>Agent Analysis</h3>")
        html.append("<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;'>")
        html.append("<tr><th>Agent</th><th>Signal</th><th>Confidence</th><th>Reasoning</th></tr>")
        for row in table_data:
            html.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
        html.append("</table>")

        action = decision.get("action", "").upper()
        decision_data = [
            ["Action", action],
            ["Quantity", decision.get("quantity")],
            ["Confidence", f"{decision.get('confidence'):.1f}%"],
            ["Reasoning", decision.get("reasoning", "")],
        ]

        html.append("<h3>Trading Decision</h3>")
        html.append("<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;'>")
        for row in decision_data:
            html.append(f"<tr><th>{row[0]}</th><td>{row[1]}</td></tr>")
        html.append("</table>")

    html.append("<h2>Portfolio Summary</h2>")
    summary_data = []
    portfolio_manager_reasoning = None
    for ticker, decision in decisions.items():
        if not portfolio_manager_reasoning and decision.get("reasoning"):
            portfolio_manager_reasoning = decision["reasoning"]
        action = decision.get("action", "").upper()
        summary_data.append([
            ticker,
            action,
            decision.get("quantity"),
            f"{decision.get('confidence'):.1f}%"
        ])

    html.append("<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;'>")
    html.append("<tr><th>Ticker</th><th>Action</th><th>Quantity</th><th>Confidence</th></tr>")
    for row in summary_data:
        html.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    html.append("</table>")

    if portfolio_manager_reasoning:
        html.append("<h3>Portfolio Strategy</h3>")
        if isinstance(portfolio_manager_reasoning, dict):
            reasoning_text = json.dumps(portfolio_manager_reasoning, indent=2)
        else:
            reasoning_text = str(portfolio_manager_reasoning)
        reasoning_text = reasoning_text.replace("\n", "<br>")
        html.append(f"<p>{reasoning_text}</p>")

    html.append("</body></html>")
    return "\n".join(html)


def send_email_output(content: str, subject="📈 AI Hedge Fund Output"):
    from_email = os.environ.get("EMAIL_USER")
    to_emails = os.environ.get("EMAIL_TO", "").split(",")
    app_password = os.environ.get("EMAIL_PASSWORD")
    smtp_host = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("EMAIL_PORT", 587))

    for to_email in to_emails:
        to_email = to_email.strip()
        if not to_email:
            continue

        msg = MIMEText(content, "html")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(from_email, app_password)
            server.send_message(msg)

        print(f"[INFO] Email sent to {to_email}")


def send_telegram_output(result: dict):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[WARN] Telegram not configured. Skipping.")
        return

    decisions = result.get("decisions")
    analyst_signals = result.get("analyst_signals", {})
    if not decisions:
        return

    message_lines = ["<b>📈 AI Hedge Fund Report</b>"]

    run_params = result.get("run_parameters", {})
    start = run_params.get("start_date")
    end = run_params.get("end_date")
    if start and end:
        message_lines.append(f"<i>Period: {start} to {end}</i>")

    for ticker, decision in decisions.items():
        message_lines.append(f"\n<b>📌 {ticker}</b>")
        action = decision.get("action", "").upper()
        qty = decision.get("quantity")
        confidence = decision.get("confidence")
        reasoning = decision.get("reasoning", "")

        message_lines.append(f"Action: <b>{action}</b>")
        message_lines.append(f"Quantity: <code>{qty}</code>")
        message_lines.append(f"Confidence: {confidence:.1f}%")
        if reasoning:
            trimmed = str(reasoning)
            if len(trimmed) > 400:
                trimmed = trimmed[:400] + "..."
            message_lines.append(f"Reasoning: {trimmed}")

        # Agent signals section
        agent_lines = ["\n— Agent Signals —"]
        for agent_key, signals in analyst_signals.items():
            if ticker not in signals or agent_key == "risk_management_agent":
                continue
            signal = signals[ticker]
            agent_name = agent_key.replace("_agent", "").replace("_", " ").title()
            sig = signal.get("signal", "").upper()
            conf = signal.get("confidence", 0)
            reason = signal.get("reasoning", "")
            agent_lines.append(f"🧠 <b>{agent_name}</b>: {sig} ({conf:.1f}%)")
            if reason:
                short_reason = str(reason)
                if len(short_reason) > 200:
                    short_reason = short_reason[:200] + "..."
                agent_lines.append(f"↳ {short_reason}")
        message_lines.extend(agent_lines)

    # Add portfolio reasoning if any
    for decision in decisions.values():
        if decision.get("reasoning"):
            message_lines.append("\n<b>📊 Portfolio Strategy</b>")
            message_lines.append(decision["reasoning"][:500] + ("..." if len(decision["reasoning"]) > 500 else ""))
            break

    text = "\n".join(message_lines)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, data={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    })

    if response.ok:
        print("[INFO] Telegram message sent.")
    else:
        print("[ERROR] Failed to send Telegram message:", response.text)
