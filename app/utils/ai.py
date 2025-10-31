import os
from flask import current_app
from openai import OpenAI


def _heuristic_insights(rent_data, lodge_data):
    # Simple, local summary that works without OpenAI
    try:
        total_rent = sum(float(t.get('rent_amount') or 0) for t in rent_data)
        tenant_count = len(rent_data)
        avg_rent = (total_rent / tenant_count) if tenant_count else 0

        checked_in = sum(1 for g in lodge_data if (g.get('status') or '') == 'checked_in')
        daily_cnt = sum(1 for g in lodge_data if (g.get('stay_type') or '') == 'daily')
        monthly_cnt = sum(1 for g in lodge_data if (g.get('stay_type') or '') == 'monthly')

        alerts = []
        if tenant_count == 0:
            alerts.append('No active tenants')
        if checked_in == 0:
            alerts.append('Lodge occupancy is 0')
        if avg_rent and avg_rent < 8000:
            alerts.append('Average rent per tenant is low')
        alerts_text = '; '.join(alerts) if alerts else 'No critical alerts'

        return {
            'ok': True,
            'rent_performance': f"Collecting ₹{total_rent:,.0f} from {tenant_count} tenants (avg ₹{avg_rent:,.0f}).",
            'occupancy_forecast': f"{checked_in} active lodge guests now; short-term occupancy expected to be steady.",
            'alerts': alerts_text,
            'lodge_trends': f"Daily: {daily_cnt}, Monthly: {monthly_cnt}. Keep a healthy mix to stabilize revenue.",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def analyze_data(rent_data, lodge_data):
    # If no API key, return heuristic insights instead of an error
    api_key = current_app.config.get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not api_key:
        return _heuristic_insights(rent_data, lodge_data)

    try:
        client = OpenAI(api_key=api_key)

        prompt = (
            "You are an analyst for a small property & lodge business. "
            "Given two JSON arrays: rent_data (tenants with rent_amount) and lodge_data (guests with stay_type/status/total_amount), "
            "summarize: 1) rent collection performance, 2) occupancy forecast, 3) alerts (low income, vacant rooms), 4) lodge daily vs monthly trend. "
            "Return a compact JSON with keys rent_performance, occupancy_forecast, alerts, lodge_trends. Keep it short and practical."
        )

        # Using Responses API for GPT-4.1
        resp = client.responses.create(
            model="gpt-4.1",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "text", "text": f"rent_data: {rent_data}"},
                        {"type": "text", "text": f"lodge_data: {lodge_data}"},
                        {"type": "text", "text": "Respond with only valid JSON."},
                    ],
                }
            ],
            temperature=0.2,
        )

        text = resp.output_text
        import json
        data = json.loads(text)
        return {"ok": True, **data}
    except Exception:
        # Fallback to local heuristic if API fails for any reason
        return _heuristic_insights(rent_data, lodge_data)
