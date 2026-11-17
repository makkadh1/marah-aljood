import sqlite3
import webbrowser
import threading
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, request, redirect, url_for, render_template_string, send_file, jsonify

app = Flask(__name__)
DB_NAME = "marah_aljood_pro.db"

# ==========================================
# 1. قاعدة البيانات الشاملة (Database Layer)
# ==========================================
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # جدول القطيع الشامل
    c.execute('''CREATE TABLE IF NOT EXISTS flock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_number TEXT UNIQUE NOT NULL,
        category TEXT NOT NULL, -- فحول، أمهات (نعاج)، طليان/رخال تسمين، مواليد
        gender TEXT NOT NULL,
        breed TEXT,
        birth_date TEXT,
        mother_tag TEXT,
        purchase_cost REAL DEFAULT 0,
        weight REAL DEFAULT 0,
        status TEXT DEFAULT 'نشط', -- نشط، مباع، نافق، مستبعد
        notes TEXT
    )''')
    
    # جدول الحركات المالية
    c.execute('''CREATE TABLE IF NOT EXISTS finance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        type TEXT NOT NULL, -- إيراد أو مصروف
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        payment_method TEXT DEFAULT 'نقدي / شبكة',
        description TEXT
    )''')
    
    # جدول الموازنة الشهرية
    c.execute('''CREATE TABLE IF NOT EXISTS budgets (
        category TEXT PRIMARY KEY,
        monthly_limit REAL DEFAULT 0
    )''')
    
    # جدول الأعلاف والمستودع
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT NOT NULL,
        unit TEXT NOT NULL,
        quantity REAL NOT NULL,
        unit_cost REAL DEFAULT 0,
        daily_usage REAL DEFAULT 0,
        last_updated TEXT
    )''')
    
    # جدول الصحة، التكاثر، والولادات
    c.execute('''CREATE TABLE IF NOT EXISTS health_breeding (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_number TEXT NOT NULL,
        event_type TEXT NOT NULL, -- تلقيح (قرع)، ولادة، تطعيم/تحصين، علاج بيطري، قص صوف/حوافر
        event_date TEXT NOT NULL,
        next_due_date TEXT,
        cost REAL DEFAULT 0,
        details TEXT
    )''')

    default_categories = [
        'أعلاف (شعير/برسيم/مكعبات)',
        'أدوية وبيطرة',
        'رواتب عمالة ومصاريف إدارية',
        'صيانة ومحروقات ومعدات',
        'شراء أغنام جديدة',
        'مصاريف تشغيلية أخرى',
        'مبيعات ذبائح وطليان',
        'مبيعات أمهات / فحول',
        'إيرادات أخرى (سماد/صوف)'
    ]
    for cat in default_categories:
        c.execute("INSERT OR IGNORE INTO budgets (category, monthly_limit) VALUES (?, 0)", (cat,))

    conn.commit()
    conn.close()

# ==========================================
# 2. محرك التحليل المالي والتقارير
# ==========================================
def generate_financial_report(period_type, target_date):
    conn = get_db()
    c = conn.cursor()
    
    if period_type == 'daily':
        like_pattern = f"{target_date}%"
        period_label = f"التقرير اليومي لتاريخ: {target_date}"
    elif period_type == 'yearly':
        like_pattern = f"{target_date[:4]}%"
        period_label = f"الميزانية السنوية لعام: {target_date[:4]}"
    else:
        like_pattern = f"{target_date[:7]}%"
        period_label = f"الموازنة والتقرير الشهري لشهر: {target_date[:7]}"

    income = c.execute("SELECT COALESCE(SUM(amount), 0) FROM finance WHERE type='إيراد' AND date LIKE ?", (like_pattern,)).fetchone()[0]
    expense = c.execute("SELECT COALESCE(SUM(amount), 0) FROM finance WHERE type='مصروف' AND date LIKE ?", (like_pattern,)).fetchone()[0]
    net = income - expense
    margin = round((net / income * 100), 1) if income > 0 else 0

    expense_breakdown = c.execute('''
        SELECT f.category, SUM(f.amount) as total, COALESCE(b.monthly_limit, 0) as budget_limit
        FROM finance f
        LEFT JOIN budgets b ON f.category = b.category
        WHERE f.type='مصروف' AND f.date LIKE ?
        GROUP BY f.category
        ORDER BY total DESC
    ''', (like_pattern,)).fetchall()

    income_breakdown = c.execute('''
        SELECT category, SUM(amount) as total
        FROM finance
        WHERE type='إيراد' AND date LIKE ?
        GROUP BY category
        ORDER BY total DESC
    ''', (like_pattern,)).fetchall()

    active_sheep = c.execute("SELECT COUNT(*) FROM flock WHERE status='نشط'").fetchone()[0]
    cost_per_head = round((expense / active_sheep), 2) if active_sheep > 0 else 0
    herd_asset_value = c.execute("SELECT COALESCE(SUM(purchase_cost), 0) FROM flock WHERE status='نشط'").fetchone()[0]
    transactions = c.execute("SELECT * FROM finance WHERE date LIKE ? ORDER BY date DESC, id DESC", (like_pattern,)).fetchall()
    
    conn.close()
    return {
        'period_label': period_label, 'income': income, 'expense': expense, 'net': net,
        'margin': margin, 'cost_per_head': cost_per_head, 'herd_asset_value': herd_asset_value,
        'expense_breakdown': expense_breakdown, 'income_breakdown': income_breakdown, 'transactions': transactions
    }

# ==========================================
# 3. واجهة المستخدم الرسومية المتكاملة (HTML)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>مراح الجود - النظام الشامل لإدارة الأغنام والمالية</title>
    <style>
        :root { --primary: #1b4332; --secondary: #2d6a4f; --accent: #e9f5db; --bg: #f4f6f5; --text: #1f2937; --danger: #dc2626; --success: #15803d; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 0; }
        header { background: var(--primary); color: white; padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; }
        header h1 { margin: 0; font-size: 21px; }
        .badge { background: rgba(255,255,255,0.15); padding: 5px 12px; border-radius: 20px; font-size: 12px; }
        nav { background: var(--secondary); padding: 10px 30px; display: flex; gap: 8px; flex-wrap: wrap; }
        nav button { background: rgba(255,255,255,0.12); border: none; color: white; padding: 9px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: bold; }
        nav button.active, nav button:hover { background: white; color: var(--primary); }
        .container { max-width: 1250px; margin: 20px auto; padding: 0 20px; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .card { background: white; padding: 18px; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); border-right: 4px solid var(--secondary); }
        .card h3 { margin: 0 0 8px 0; font-size: 13px; color: #6b7280; }
        .card .val { font-size: 22px; font-weight: bold; color: var(--primary); }
        .box { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); margin-bottom: 20px; }
        h2 { margin-top: 0; color: var(--primary); border-bottom: 2px solid var(--accent); padding-bottom: 8px; font-size: 17px; }
        form.grid-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; align-items: end; }
        label { display: block; font-size: 12px; margin-bottom: 4px; font-weight: bold; color: #374151; }
        input, select { width: 100%; padding: 8px; border: 1px solid #d1d5db; border-radius: 5px; box-sizing: border-box; font-size: 13px; }
        button.btn { background: var(--secondary); color: white; border: none; padding: 9px 14px; border-radius: 5px; cursor: pointer; font-weight: bold; font-size: 13px; }
        button.btn:hover { background: var(--primary); }
        button.btn-danger { background: var(--danger); padding: 4px 8px; font-size: 12px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 9px; text-align: right; border-bottom: 1px solid #e5e7eb; font-size: 13px; }
        th { background: var(--accent); color: var(--primary); }
        .income { color: var(--success); font-weight: bold; }
        .expense { color: var(--danger); font-weight: bold; }
        .alert { background: #fef3c7; border-right: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 8px; border-radius: 5px; font-size: 13px; }
        .filter-bar { background: #eef2f0; padding: 12px; border-radius: 8px; margin-bottom: 20px; display: flex; gap: 12px; align-items: end; flex-wrap: wrap; }
        @media print { nav, .filter-bar, .no-print { display: none !important; } }
    </style>
</head>
<body>

<header>
    <h1>🐑 مراح الجود | النظام الشامل لإدارة الأغنام والشؤون المالية</h1>
    <span class="badge">🔒 يعمل بدون إنترنت | الملكية المطلقة</span>
</header>

<nav>
    <button class="tab-btn active" onclick="openTab('reports', this)">📊 التقارير والموازنة</button>
    <button class="tab-btn" onclick="openTab('flock', this)">🐑 إدارة القطيع والأصول ({{ active_count }})</button>
    <button class="tab-btn" onclick="openTab('finance', this)">💰 الشؤون المالية والقيود</button>
    <button class="tab-btn" onclick="openTab('inventory', this)">🌾 مستودع الأعلاف</button>
    <button class="tab-btn" onclick="openTab('health', this)">🩺 البيطرة والتكاثر</button>
</nav>

<div class="container">

    <!-- 1. التقارير والموازنة -->
    <div id="reports" class="tab-content active">
        <div class="filter-bar">
            <form action="/" method="GET" style="display:flex; gap:10px; align-items:end; flex-wrap:wrap; width:100%;">
                <div>
                    <label>نوع التقرير:</label>
                    <select name="period">
                        <option value="monthly" {{ 'selected' if period=='monthly' }}>موازنة شهرية</option>
                        <option value="daily" {{ 'selected' if period=='daily' }}>تقرير يومي</option>
                        <option value="yearly" {{ 'selected' if period=='yearly' }}>ميزانية سنوية</option>
                    </select>
                </div>
                <div>
                    <label>التاريخ / الشهر:</label>
                    <input type="date" name="target_date" value="{{ target_date }}">
                </div>
                <button type="submit" class="btn">🔍 عرض التقرير</button>
                <button type="button" class="btn" style="background:#374151;" onclick="window.print()">🖨️ طباعة التقرير</button>
                <a href="/export_finance?period={{ period }}&target_date={{ target_date }}"><button type="button" class="btn" style="background:#0f766e;">📥 تصدير Excel</button></a>
                <a href="/backup_db"><button type="button" class="btn" style="background:#4b5563;">🛡️ نسخة احتياطية</button></a>
            </form>
        </div>

        {% if alerts %}
        <div class="box no-print">
            <h2>🔔 التنبيهات الذكية للمراح</h2>
            {% for a in alerts %}<div class="alert">{{ a }}</div>{% endfor %}
        </div>
        {% endif %}

        <div class="box">
            <h2>📈 {{ report.period_label }}</h2>
            <div class="cards">
                <div class="card"><h3>إجمالي الإيرادات</h3><div class="val income">{{ "%.2f"|format(report.income) }} ر.س</div></div>
                <div class="card"><h3>إجمالي المصروفات</h3><div class="val expense">{{ "%.2f"|format(report.expense) }} ر.س</div></div>
                <div class="card"><h3>صافي الربح / الخسارة</h3><div class="val" style="color: {{ '#15803d' if report.net >= 0 else '#dc2626' }}">{{ "%.2f"|format(report.net) }} ر.س</div></div>
                <div class="card"><h3>هامش الربحية</h3><div class="val">{{ report.margin }}%</div></div>
                <div class="card"><h3>تكلفة الرأس (للفترة)</h3><div class="val">{{ "%.2f"|format(report.cost_per_head) }} ر.س</div></div>
                <div class="card"><h3>قيمة الأصول الحية</h3><div class="val">{{ "%.2f"|format(report.herd_asset_value) }} ر.س</div></div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px;">
                <div>
                    <h3>📉 تحليل المصروفات</h3>
                    <table>
                        <tr><th>البند</th><th>المبلغ</th><th>النسبة</th></tr>
                        {% for item in report.expense_breakdown %}
                        {% set pct = (item['total'] / report.expense * 100) if report.expense > 0 else 0 %}
                        <tr><td><b>{{ item['category'] }}</b></td><td class="expense">{{ "%.2f"|format(item['total']) }} ر.س</td><td>{{ "%.1f"|format(pct) }}%</td></tr>
                        {% endfor %}
                    </table>
                </div>
                <div>
                    <h3>📈 تحليل الإيرادات</h3>
                    <table>
                        <tr><th>البند</th><th>المبلغ</th><th>النسبة</th></tr>
                        {% for item in report.income_breakdown %}
                        {% set pct = (item['total'] / report.income * 100) if report.income > 0 else 0 %}
                        <tr><td><b>{{ item['category'] }}</b></td><td class="income">{{ "%.2f"|format(item['total']) }} ر.س</td><td>{{ "%.1f"|format(pct) }}%</td></tr>
                        {% endfor %}
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- 2. إدارة القطيع والأصول -->
    <div id="flock" class="tab-content">
        <div class="box">
            <h2>➕ تسجيل رأس جديد في القطيع</h2>
            <form class="grid-form" action="/add_sheep" method="POST">
                <div><label>رقم الترقيم (الأذن)*</label><input type="text" name="tag_number" required placeholder="مثال: 101"></div>
                <div><label>التصنيف والفئة</label>
                    <select name="category">
                        <option>أمهات (نعاج منتجة)</option>
                        <option>فحول (ذكور للقرع)</option>
                        <option>رخال وطليان تسمين</option>
                        <option>مواليد جديدة</option>
                    </select>
                </div>
                <div><label>الجنس</label><select name="gender"><option>أنثى</option><option>ذكر</option></select></div>
                <div><label>السلالة</label><input type="text" name="breed" placeholder="حري / نعيمي"></div>
                <div><label>تاريخ الميلاد/الشراء</label><input type="date" name="birth_date" value="{{ today }}"></div>
                <div><label>تكلفة الشراء / القيمة (ر.س)</label><input type="number" step="1" name="purchase_cost" value="0"></div>
                <div><label>رقم الأم</label><input type="text" name="mother_tag"></div>
                <button type="submit" class="btn">حفظ في القطيع</button>
            </form>
        </div>

        <div class="box">
            <h2>📋 سجل القطيع الفعلي والنشط</h2>
            <table>
                <tr><th>الرقم</th><th>الفئة</th><th>الجنس</th><th>السلالة</th><th>القيمة</th><th>الحالة</th><th>إجراءات سريعة</th></tr>
                {% for s in flock %}
                <tr>
                    <td><b>{{ s['tag_number'] }}</b></td><td>{{ s['category'] }}</td><td>{{ s['gender'] }}</td><td>{{ s['breed'] }}</td>
                    <td>{{ s['purchase_cost'] }} ر.س</td><td><b>{{ s['status'] }}</b></td>
                    <td>
                        {% if s['status'] == 'نشط' %}
                        <div style="display:flex; gap:5px;">
                            <form action="/sell_sheep/{{ s['id'] }}" method="POST" style="display:flex; gap:3px;">
                                <input type="number" name="price" placeholder="سعر البيع" required style="width:80px; padding:3px;">
                                <button type="submit" class="btn" style="padding:3px 6px; font-size:11px;">بيع</button>
                            </form>
                            <a href="/mark_dead/{{ s['id'] }}" onclick="return confirm('تسجيل حالة نفوق؟')"><button class="btn btn-danger">نفوق</button></a>
                        </div>
                        {% else %}-{% endif %}
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>

    <!-- 3. الشؤون المالية والقيود -->
    <div id="finance" class="tab-content">
        <div class="box">
            <h2>💳 تسجيل قيد مالي جديد</h2>
            <form class="grid-form" action="/add_finance" method="POST">
                <div><label>التاريخ</label><input type="date" name="date" value="{{ today }}" required></div>
                <div><label>النوع</label><select name="type"><option value="مصروف">مصروف (-)</option><option value="إيراد">إيراد (+)</option></select></div>
                <div><label>البند المحاسبي</label>
                    <select name="category">
                        <option>أعلاف (شعير/برسيم/مكعبات)</option>
                        <option>أدوية وبيطرة</option>
                        <option>رواتب عمالة ومصاريف إدارية</option>
                        <option>صيانة ومحروقات ومعدات</option>
                        <option>شراء أغنام جديدة</option>
                        <option>مصاريف تشغيلية أخرى</option>
                        <option>مبيعات ذبائح وطليان</option>
                        <option>مبيعات أمهات / فحول</option>
                        <option>إيرادات أخرى (سماد/صوف)</option>
                    </select>
                </div>
                <div><label>المبلغ (ر.س)*</label><input type="number" step="0.01" name="amount" required></div>
                <div><label>طريقة الدفع</label><select name="payment_method"><option>نقدي / شبكة</option><option>تحويل بنكي</option><option>آجل</option></select></div>
                <div><label>البيان والتفاصيل</label><input type="text" name="description"></div>
                <button type="submit" class="btn">حفظ القيد</button>
            </form>
        </div>

        <div class="box">
            <h2>🎯 ضبط سقوف الموازنة الشهرية</h2>
            <form class="grid-form" action="/update_budgets" method="POST">
                {% for b in budgets %}
                <div>
                    <label>{{ b['category'] }}</label>
                    <input type="number" step="10" name="limit_{{ b['category'] }}" value="{{ b['monthly_limit'] }}">
                </div>
                {% endfor %}
                <button type="submit" class="btn">حفظ الموازنة</button>
            </form>
        </div>

        <div class="box">
            <h2>📒 سجل الحركات المالية الأخيرة</h2>
            <table>
                <tr><th>التاريخ</th><th>النوع</th><th>البند</th><th>المبلغ</th><th>البيان</th><th>حذف</th></tr>
                {% for f in all_finances %}
                <tr>
                    <td>{{ f['date'] }}</td>
                    <td class="{{ 'income' if f['type']=='إيراد' else 'expense' }}">{{ f['type'] }}</td>
                    <td>{{ f['category'] }}</td>
                    <td class="{{ 'income' if f['type']=='إيراد' else 'expense' }}">{{ "%.2f"|format(f['amount']) }} ر.س</td>
                    <td>{{ f['description'] }}</td>
                    <td><a href="/delete_finance/{{ f['id'] }}"><button class="btn btn-danger">حذف</button></a></td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>

    <!-- 4. مستودع الأعلاف -->
    <div id="inventory" class="tab-content">
        <div class="box">
            <h2>📦 توريد أعلاف للمستودع</h2>
            <form class="grid-form" action="/add_inventory" method="POST">
                <div><label>اسم الصنف*</label><input type="text" name="item_name" required placeholder="شعير / برسيم"></div>
                <div><label>الوحدة</label><select name="unit"><option>كيس</option><option>بالة / لبنة</option><option>طن</option></select></div>
                <div><label>الكمية المضافة*</label><input type="number" step="0.1" name="quantity" required></div>
                <div><label>الاستهلاك اليومي</label><input type="number" step="0.1" name="daily_usage" value="1"></div>
                <div><label>التكلفة الإجمالية (تُسجل كمصروف)</label><input type="number" step="0.01" name="cost" value="0"></div>
                <button type="submit" class="btn">إضافة للمستودع</button>
            </form>
        </div>
        <div class="box">
            <h2>🏪 الأرصدة الحالية</h2>
            <table>
                <tr><th>الصنف</th><th>الكمية المتبقية</th><th>الاستهلاك اليومي</th><th>يكفي لمدة</th><th>خصم استهلاك</th></tr>
                {% for i in inventory %}
                <tr>
                    <td><b>{{ i['item_name'] }}</b></td><td>{{ i['quantity'] }} {{ i['unit'] }}</td><td>{{ i['daily_usage'] }} {{ i['unit'] }}</td>
                    <td>{% if i['daily_usage'] > 0 %}{{ (i['quantity'] / i['daily_usage'])|int }} يوم{% else %}-{% endif %}</td>
                    <td>
                        <form action="/consume_inventory/{{ i['id'] }}" method="POST" style="display:flex; gap:5px;">
                            <input type="number" step="0.1" name="used" value="{{ i['daily_usage'] }}" style="width:70px; padding:3px;">
                            <button type="submit" class="btn" style="padding:3px 6px; font-size:11px;">خصم</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>

    <!-- 5. البيطرة والتكاثر -->
    <div id="health" class="tab-content">
        <div class="box">
            <h2>🩺 تسجيل حدث بيطري أو تناسلي</h2>
            <form class="grid-form" action="/add_health" method="POST">
                <div><label>رقم الرأس / المجموعة*</label><input type="text" name="tag_number" required placeholder="101 أو الكل"></div>
                <div><label>نوع الحدث</label>
                    <select name="event_type">
                        <option>تلقيح (قرع)</option>
                        <option>ولادة جديدة</option>
                        <option>تطعيم / تحصين دوري</option>
                        <option>علاج بيطري فردي</option>
                        <option>قص صوف أو حوافر</option>
                    </select>
                </div>
                <div><label>تاريخ الحدث</label><input type="date" name="event_date" value="{{ today }}" required></div>
                <div><label>موعد المتابعة / الولادة المتوقع</label><input type="date" name="next_due_date"></div>
                <div><label>التكلفة (تُسجل كمصروف)</label><input type="number" step="0.01" name="cost" value="0"></div>
                <div><label>التفاصيل / الأدوية المستخدمة</label><input type="text" name="details"></div>
                <button type="submit" class="btn">حفظ السجل</button>
            </form>
        </div>
        <div class="box">
            <h2>📋 السجل البيطري والتناسلي</h2>
            <table>
                <tr><th>الرقم</th><th>الحدث</th><th>التاريخ</th><th>الموعد القادم</th><th>التكلفة</th><th>التفاصيل</th></tr>
                {% for h in health %}
                <tr><td><b>{{ h['tag_number'] }}</b></td><td>{{ h['event_type'] }}</td><td>{{ h['event_date'] }}</td><td>{{ h['next_due_date'] or '-' }}</td><td>{{ h['cost'] }} ر.س</td><td>{{ h['details'] }}</td></tr>
                {% endfor %}
            </table>
        </div>
    </div>

</div>

<script>
function openTab(tabId, btn) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    btn.classList.add('active');
}
</script>
</body>
</html>
"""

# ==========================================
# 4. مسارات وخوارزميات التطبيق (Flask Routes)
# ==========================================
@app.route('/')
def index():
    today_str = datetime.now().strftime('%Y-%m-%d')
    period = request.args.get('period', 'monthly')
    target_date = request.args.get('target_date', today_str)
    
    report = generate_financial_report(period, target_date)
    conn = get_db()
    flock = conn.execute("SELECT * FROM flock ORDER BY id DESC").fetchall()
    active_count = conn.execute("SELECT COUNT(*) FROM flock WHERE status='نشط'").fetchone()[0]
    all_finances = conn.execute("SELECT * FROM finance ORDER BY date DESC, id DESC LIMIT 100").fetchall()
    budgets = conn.execute("SELECT * FROM budgets").fetchall()
    inventory = conn.execute("SELECT * FROM inventory").fetchall()
    health = conn.execute("SELECT * FROM health_breeding ORDER BY event_date DESC").fetchall()
    
    alerts = []
    for item in inventory:
        if item['daily_usage'] > 0 and (item['quantity'] / item['daily_usage']) <= 5:
            alerts.append(f"⚠️ تنبيه مخزون: صنف ({item['item_name']}) يوشك على النفاد (يكفي لـ {int(item['quantity']/item['daily_usage'])} أيام).")
            
    for exp in report['expense_breakdown']:
        if exp['budget_limit'] > 0 and period == 'monthly' and exp['total'] > exp['budget_limit']:
            alerts.append(f"🚨 تجاوز موازنة: بند ({exp['category']}) تجاوز السقف المخصص للشهر.")

    next_week = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    upcoming = conn.execute("SELECT * FROM health_breeding WHERE next_due_date BETWEEN ? AND ?", (today_str, next_week)).fetchall()
    for u in upcoming:
        alerts.append(f"📅 موعد قادم خلال أسبوع: ({u['event_type']}) للرقم [{u['tag_number']}] بتاريخ {u['next_due_date']}.")
        
    conn.close()
    return render_template_string(HTML_TEMPLATE, report=report, period=period, target_date=target_date,
                                  flock=flock, active_count=active_count, all_finances=all_finances,
                                  budgets=budgets, inventory=inventory, health=health, alerts=alerts, today=today_str)

@app.route('/add_sheep', methods=['POST'])
def add_sheep():
    conn = get_db()
    try:
        conn.execute("INSERT INTO flock (tag_number, category, gender, breed, birth_date, purchase_cost, mother_tag) VALUES (?,?,?,?,?,?,?)",
                     (request.form['tag_number'], request.form['category'], request.form['gender'],
                      request.form['breed'], request.form['birth_date'], float(request.form['purchase_cost'] or 0), request.form['mother_tag']))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for('index'))

@app.route('/sell_sheep/<int:sheep_id>', methods=['POST'])
def sell_sheep(sheep_id):
    price = float(request.form['price'])
    conn = get_db()
    row = conn.execute("SELECT tag_number, category FROM flock WHERE id=?", (sheep_id,)).fetchone()
    conn.execute("UPDATE flock SET status='مباع' WHERE id=?", (sheep_id,))
    conn.execute("INSERT INTO finance (date, type, category, amount, description) VALUES (?,?,?,?,?)",
                 (datetime.now().strftime('%Y-%m-%d'), 'إيراد', 'مبيعات ذبائح وطليان', price, f"بيع {row['category']} رقم {row['tag_number']}"))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/mark_dead/<int:sheep_id>')
def mark_dead(sheep_id):
    conn = get_db()
    conn.execute("UPDATE flock SET status='نافق' WHERE id=?", (sheep_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/add_finance', methods=['POST'])
def add_finance():
    conn = get_db()
    conn.execute("INSERT INTO finance (date, type, category, amount, payment_method, description) VALUES (?,?,?,?,?,?)",
                 (request.form['date'], request.form['type'], request.form['category'],
                  float(request.form['amount']), request.form['payment_method'], request.form['description']))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/update_budgets', methods=['POST'])
def update_budgets():
    conn = get_db()
    for key, val in request.form.items():
        if key.startswith('limit_'):
            cat = key.replace('limit_', '')
            conn.execute("UPDATE budgets SET monthly_limit=? WHERE category=?", (float(val or 0), cat))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/delete_finance/<int:fin_id>')
def delete_finance(fin_id):
    conn = get_db()
    conn.execute("DELETE FROM finance WHERE id=?", (fin_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/add_inventory', methods=['POST'])
def add_inventory():
    name = request.form['item_name']
    qty = float(request.form['quantity'])
    cost = float(request.form['cost'] or 0)
    conn = get_db()
    existing = conn.execute("SELECT id, quantity FROM inventory WHERE item_name=?", (name,)).fetchone()
    if existing:
        conn.execute("UPDATE inventory SET quantity=?, daily_usage=?, last_updated=? WHERE id=?",
                     (existing['quantity'] + qty, float(request.form['daily_usage']), datetime.now().strftime('%Y-%m-%d'), existing['id']))
    else:
        conn.execute("INSERT INTO inventory (item_name, unit, quantity, daily_usage, last_updated) VALUES (?,?,?,?,?)",
                     (name, request.form['unit'], qty, float(request.form['daily_usage']), datetime.now().strftime('%Y-%m-%d')))
    if cost > 0:
        conn.execute("INSERT INTO finance (date, type, category, amount, description) VALUES (?,?,?,?,?)",
                     (datetime.now().strftime('%Y-%m-%d'), 'مصروف', 'أعلاف (شعير/برسيم/مكعبات)', cost, f"توريد {qty} {request.form['unit']} {name}"))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/consume_inventory/<int:inv_id>', methods=['POST'])
def consume_inventory(inv_id):
    used = float(request.form['used'])
    conn = get_db()
    conn.execute("UPDATE inventory SET quantity = MAX(0, quantity - ?) WHERE id=?", (used, inv_id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/add_health', methods=['POST'])
def add_health():
    cost = float(request.form['cost'] or 0)
    event_type = request.form['event_type']
    event_date = request.form['event_date']
    next_due = request.form['next_due_date']
    if event_type == 'تلقيح (قرع)' and not next_due:
        next_due = (datetime.strptime(event_date, '%Y-%m-%d') + timedelta(days=150)).strftime('%Y-%m-%d')
    conn = get_db()
    conn.execute("INSERT INTO health_breeding (tag_number, event_type, event_date, next_due_date, cost, details) VALUES (?,?,?,?,?,?)",
                 (request.form['tag_number'], event_type, event_date, next_due, cost, request.form['details']))
    if cost > 0:
        conn.execute("INSERT INTO finance (date, type, category, amount, description) VALUES (?,?,?,?,?)",
                     (event_date, 'مصروف', 'أدوية وبيطرة', cost, f"{event_type} - {request.form['details']}"))
    # إذا كانت ولادة جديدة، يمكن إضافتها تلقائياً كمواليد
    if event_type == 'ولادة جديدة':
        conn.execute("INSERT INTO flock (tag_number, category, gender, birth_date, mother_tag, status) VALUES (?,?,?,?,?,?)",
                     (f"مواليد_{request.form['tag_number']}_{datetime.now().strftime('%H%M')}", 'مواليد جديدة', 'أنثى/ذكر', event_date, request.form['tag_number'], 'نشط'))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/export_finance')
def export_finance():
    period = request.args.get('period', 'monthly')
    target_date = request.args.get('target_date', datetime.now().strftime('%Y-%m-%d'))
    report = generate_financial_report(period, target_date)
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['التاريخ', 'النوع', 'البند', 'طريقة الدفع', 'المبلغ (ر.س)', 'البيان'])
    for t in report['transactions']:
        writer.writerow([t['date'], t['type'], t['category'], t['payment_method'], t['amount'], t['description']])
    return send_file(io.BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv', as_attachment=True, download_name=f"report_{period}_{target_date}.csv")

@app.route('/backup_db')
def backup_db():
    return send_file(DB_NAME, as_attachment=True, download_name=f"marah_pro_backup_{datetime.now().strftime('%Y%m%d')}.db")

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)