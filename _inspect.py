import re
content = open('app.py', encoding='utf-8').read()
# Find dashboard-stats route
idx = content.find("dashboard-stats")
if idx >= 0:
    print("DASHBOARD-STATS found at char", idx)
    # Show 80 chars before and 600 after
    print(content[max(0,idx-100):idx+800])
else:
    print("NOT FOUND")

# Find kitchen analytics
idx2 = content.find("analytics")
while idx2 >= 0:
    print("\nANALYTICS at char", idx2, ":", content[idx2:idx2+80])
    idx2 = content.find("analytics", idx2+1)
