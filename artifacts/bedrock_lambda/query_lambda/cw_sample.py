import re

txt = 'tadad <special_char>176</special_char> mumbai tha ithsj lorem psoeinf '
data = re.sub('<special_char>.*</special_char>', '', txt)
print(data)
