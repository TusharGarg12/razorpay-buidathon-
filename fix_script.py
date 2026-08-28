with open('generate_report.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('figsize=(13, 6)', 'figsize=(13, 4.5)')
content = content.replace('figsize=(10, 3.5)', 'figsize=(10, 2.5)')
content = content.replace('figsize=(13, 5.5)', 'figsize=(13, 4.0)')
content = content.replace('figsize=(10, 4.5)', 'figsize=(10, 3.8)')

old = "    story.append(fig_to_image(make_dataflow(), width_cm=15.5))"
new = "    story.append(PageBreak())\n    story.append(fig_to_image(make_dataflow(), width_cm=15.5))"
content = content.replace(old, new)

with open('generate_report.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('All fixes applied')
