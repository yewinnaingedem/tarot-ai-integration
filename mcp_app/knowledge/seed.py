# mcp_app/knowledge/seed.py
from mcp_app.knowledge.store import add_knowledge, clear_all_knowledge

KNOWLEDGE = [
    # ── Business Overview ─────────────────────────────────────
    {
        "id":   "business_overview",
        "text": (
            "Pinky Tarot is a Myanmar online tarot reading platform. "
            "Frontend is KBZPay mini app where customers browse categories and packages. "
            "Customers submit orders with full name, age, date of birth, gender, remark (their question). "
            "Customers pay via KBZPay after ordering. "
            "Backend admin panel manages orders, discounts, coupons, and monitors revenue."
        ),
        "metadata": {"category": "business", "priority": "high"},
    },

    # ── Order Lifecycle ───────────────────────────────────────
    {
        "id":   "order_lifecycle",
        "text": (
            "Order status PENDING means awaiting payment OR admin has not answered yet. "
            "Order status COMPLETE means admin delivered reading AND payment received. "
            "Order status CANCELLED means order was cancelled. "
            "Both payment confirmation AND admin answer required to become COMPLETE. "
            "Unpaid orders auto-deleted after 15 days by system. "
            "Pending orders over 48 hours need urgent admin follow-up. "
            "Admin must manually mark order complete after answering."
        ),
        "metadata": {"category": "orders", "priority": "high"},
    },

    # ── Product Structure ─────────────────────────────────────
    {
        "id":   "product_structure",
        "text": (
            "Categories contain multiple packages. "
            "Each category has many packages with different prices in MMK. "
            "Discounts and coupons apply at category level or specific package level. "
            "ALWAYS call get_categories tool to get the REAL list of categories with IDs. "
            "NEVER guess or make up category names — only use what get_categories returns."
        ),
        "metadata": {"category": "products", "priority": "high"},
    },

    # ── Discount System ───────────────────────────────────────
    {
        "id":   "discount_system",
        "text": (
            "Discounts have these fields: category_id, package_ids, type (percentage or amount), "
            "amount, title, start_date, end_date. "
            "Admin creates discounts in backend panel. "
            "Discount can apply to entire category or specific packages. "
            "category_id null means apply to all categories. "
            "Discount date ranges cannot overlap for the same category. "
            "Always call get_categories before creating discount to get real category IDs."
        ),
        "metadata": {"category": "discounts", "priority": "high"},
    },

    # ── Coupon System ─────────────────────────────────────────
    {
        "id":   "coupon_system",
        "text": (
            "Coupons are system-generated unique codes in PTR format like PTRHH67A. "
            "Coupon fields: code, coupon_type (percentage or amount), amount, "
            "available_times (max uses), used_times, category_id, package_ids, "
            "start_date, end_date, with_discount (can stack with discounts), active. "
            "Usage types: one-time use, limited N times, or unlimited. "
            "Customers enter coupon code at checkout in KBZPay mini app. "
            "Coupon date ranges cannot overlap for same category."
        ),
        "metadata": {"category": "coupons", "priority": "high"},
    },

    # ── Key Metrics ───────────────────────────────────────────
    {
        "id":   "key_metrics",
        "text": (
            "Conversion rate equals completed orders divided by total orders times 100 percent. "
            "Target conversion rate is over 70 percent. "
            "Below 70 percent means slow follow-up or payment issues. "
            "At-risk revenue means pending order amounts that may be lost if not followed up. "
            "Revenue means sum of completed order total amounts in MMK. "
            "Pending orders over 48 hours need immediate admin action. "
            "Lost from pending means potential revenue not yet converted."
        ),
        "metadata": {"category": "metrics", "priority": "high"},
    },

    # ── Thingyan ─────────────────────────────────────────────
    {
        "id":   "holiday_thingyan",
        "text": (
            "Thingyan Water Festival is the BIGGEST sales event of the year for Pinky Tarot. "
            "Thingyan 2026 dates are April 11 to 19. "
            "Sales pattern: surge 7 days BEFORE festival, drop DURING festival, recover AFTER. "
            "Best strategy: launch discount April 1 to 10 before festival starts. "
            "Love and Relationship packages sell the most during Thingyan. "
            "Customers seek love and life guidance for Myanmar new year. "
            "Prepare maximum reader capacity before Thingyan. "
            "Send KBZPay push notification to past customers before Thingyan."
        ),
        "metadata": {"category": "holidays", "holiday": "thingyan", "priority": "high"},
    },

    # ── Full Moon Days ────────────────────────────────────────
    {
        "id":   "holiday_fullmoon",
        "text": (
            "Full Moon days are spiritually significant and auspicious in Myanmar. "
            "Kason Full Moon 2026 is April 30. "
            "Sales pattern: surge on the full moon day itself. "
            "Strategy: run 1-day flash discount on full moon day. "
            "Spiritual packages sell best on full moon days. "
            "Customers are more receptive to tarot readings on auspicious days."
        ),
        "metadata": {"category": "holidays", "holiday": "fullmoon", "priority": "medium"},
    },

    # ── Thadingyut ───────────────────────────────────────────
    {
        "id":   "holiday_thadingyut",
        "text": (
            "Thadingyut Festival is a major Myanmar festival of lights. "
            "Thadingyut 2025 dates are October 6 to 8. "
            "Sales pattern: pre-festival boost 3 to 5 days before festival. "
            "Strategy: launch festival-themed discount 5 days before. "
            "All categories benefit during festival seasons. "
            "Festival seasons increase spiritual curiosity among customers."
        ),
        "metadata": {"category": "holidays", "holiday": "thadingyut", "priority": "medium"},
    },

    # ── Tazaungdaing ─────────────────────────────────────────
    {
        "id":   "holiday_tazaungdaing",
        "text": (
            "Tazaungdaing Festival of lights in Myanmar. "
            "Tazaungdaing 2025 dates are November 4 to 5. "
            "Sales pattern: pre-festival boost 3 to 5 days before. "
            "Strategy: festival-themed discount 5 days before. All categories benefit."
        ),
        "metadata": {"category": "holidays", "holiday": "tazaungdaing", "priority": "medium"},
    },

    # ── Public Holidays ───────────────────────────────────────
    {
        "id":   "holiday_public",
        "text": (
            "Public holidays in Myanmar include Independence Day January 4, "
            "Union Day February 12, Peasants Day March 2, Armed Forces Day March 27, "
            "Workers Day May 1, Martyrs Day July 19, Christmas Day December 25. "
            "Sales pattern: slight boost on public holidays. "
            "Strategy: optional small discount. Lower impact than festivals."
        ),
        "metadata": {"category": "holidays", "holiday": "public", "priority": "low"},
    },

    # ── Discount Workflow ─────────────────────────────────────
    {
        "id":   "workflow_discount",
        "text": (
            "DISCOUNT CREATION WORKFLOW - always follow this exact order: "
            "Step 1: call get_categories to show all categories with IDs. "
            "Step 2: display ALL categories to user and ask which category. "
            "Step 3: if user wants specific packages call get_packages_by_category. "
            "Step 4: collect discount details: type percentage or amount, value, title, start date, end date. "
            "Step 5: call create_discount with all collected IDs and details. "
            "NEVER call create_discount without showing categories first. "
            "If user says all categories set category_id to null. "
            "If user says all packages set package_ids to null."
        ),
        "metadata": {"category": "workflows", "priority": "high"},
    },

    # ── Coupon Workflow ───────────────────────────────────────
    {
        "id":   "workflow_coupon",
        "text": (
            "COUPON CREATION WORKFLOW - always follow this exact order: "
            "Step 1: call get_categories to show all categories with IDs. "
            "Step 2: display ALL categories and ask which category and if specific packages needed. "
            "Step 3: if specific packages needed call get_packages_by_category. "
            "Step 4: collect coupon details: type percentage or amount, amount value, "
            "available_times max uses, start_date, end_date, with_discount stackable. "
            "Step 5: call create_coupon. Code is auto-generated in PTR format. "
            "NEVER call create_coupon without showing categories first."
        ),
        "metadata": {"category": "workflows", "priority": "high"},
    },

    # ── Order Date Workflow ───────────────────────────────────
    {
        "id":   "workflow_orders_date",
        "text": (
            "When user asks for orders by date calculate YYYY-MM-DD dates: "
            "today means current date to current date. "
            "yesterday means yesterday date to yesterday date. "
            "this month means first day of current month to today. "
            "last month means first day of last month to last day of last month. "
            "last 7 days means 7 days ago to today. "
            "last 30 days means 30 days ago to today. "
            "specific date like March 21 2026 means 2026-03-21 to 2026-03-21. "
            "specific month like March 2026 means 2026-03-01 to 2026-03-31. "
            "Always calculate actual YYYY-MM-DD dates before calling get_order_by_date."
        ),
        "metadata": {"category": "workflows", "priority": "high"},
    },

    # ── Currency Rules ────────────────────────────────────────
    {
        "id":   "currency_rules",
        "text": (
            "All prices and revenue are in Myanmar Kyat MMK. "
            "Always format currency with commas: 9,000 MMK not 9000. "
            "Never use USD dollars or other currencies. "
            "Typical package prices range from 5000 to 20000 MMK. "
            "When showing revenue always include MMK suffix."
        ),
        "metadata": {"category": "rules", "priority": "medium"},
    },

    # ── Response Rules ────────────────────────────────────────
    {
        "id":   "response_rules",
        "text": (
            "Always respond in the same language the user uses English or Myanmar Burmese. "
            "Never say Final Answer just give the answer directly. "
            "Never mention tool names in responses. "
            "Never fabricate numbers revenue or statistics always use tools for real data. "
            "Never reference Google Data Studio or external reports. "
            "For pending orders always show urgency level and recommend action. "
            "For discounts confirm all details after creation. "
            "Keep responses concise with bullet points for lists. "
            "Address user by their name when known."
        ),
        "metadata": {"category": "rules", "priority": "high"},
    },

    # ── Sales Strategy ────────────────────────────────────────
    {
        "id":   "sales_strategy",
        "text": (
            "To improve sales follow up pending orders within 6 hours to boost conversion. "
            "Discount underperforming packages with less than 40 percent conversion rate. "
            "Amplify top selling packages by promoting them more. "
            "Run promotions on highest revenue days of the week. "
            "Before major holidays prepare discounts 7 to 10 days in advance. "
            "During Thingyan pre-period focus on Love and Relationship packages. "
            "Monitor at-risk revenue from pending orders approaching 15-day deletion."
        ),
        "metadata": {"category": "strategy", "priority": "medium"},
    },

    # ── Admin Capabilities ────────────────────────────────────
    {
        "id":   "admin_capabilities",
        "text": (
            "Admin assistant capabilities: "
            "View latest orders and orders by date range. "
            "Get order summary stats for today yesterday this week this month last month. "
            "Get pending orders needing follow-up. "
            "Analyze package performance best and worst sellers. "
            "View revenue trends daily or weekly. "
            "Get AI sales suggestions and recommendations. "
            "View and create discounts for categories and packages. "
            "View create update and deactivate coupons. "
            "Analyze holiday sales and prepare holiday strategies. "
            "Compare holiday sales year over year."
        ),
        "metadata": {"category": "capabilities", "priority": "medium"},
    },
    {
        "id":   "greeting_capabilities",
        "text": (
            "When user asks what can you do, hello, hi, or mingalaba respond with: "
            "Hello! I am your Pinky Tarot admin assistant. "
            "I can help you with: "
            "Orders - view latest orders check by date follow up pending orders. "
            "Revenue - today sales trends conversion rates. "
            "Discounts - create view deactivate promotions. "
            "Packages - performance analysis best and worst sellers. "
            "Coupons - create view manage coupon codes. "
            "AI Suggestions - recommendations to boost revenue. "
            "Holiday Planning - prepare sales strategy for upcoming holidays. "
            "Just tell me what you need!"
        ),
        "metadata": {"category": "greeting", "priority": "high"},
    },
]


def seed():
    print("🌱 Seeding Pinky Tarot knowledge base...")
    clear_all_knowledge()
    add_knowledge(KNOWLEDGE)
    print(f"✅ Seeded {len(KNOWLEDGE)} knowledge entries")
    print("\nKnowledge categories added:")
    categories = {}
    for k in KNOWLEDGE:
        cat = k["metadata"].get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in categories.items():
        print(f"  {cat}: {count} entries")


if __name__ == "__main__":
    seed()