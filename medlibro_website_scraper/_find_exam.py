import re
p = r"c:\Users\PRO\Desktop\New folder (4)\scraping\requests\medlibro_website_scraper\mirror\assets\index-AtrV5JHa.js"
s = open(p, encoding="utf-8", errors="ignore").read()
for m in re.finditer(r'\{version:\d+,name:"exam"[^}]+', s):
    print(m.group(0))
# also path learn
for m in re.finditer(r'name:"[^"]*exam[^"]*"', s):
    print(m.group(0)[:120])
