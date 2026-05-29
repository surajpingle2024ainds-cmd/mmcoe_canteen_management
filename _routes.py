import re
content = open('app.py', encoding='utf-8').read()
routes = re.findall(r"@app\.route\('([^']+)'", content)
for r in sorted(set(routes)):
    if any(k in r for k in ['owner', 'kitchen', 'health', 'alert', 'order', 'analytic']):
        print(r)
