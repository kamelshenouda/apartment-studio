#!/usr/bin/env python3
"""Keep private words (family names, an exact address, a phone number) off the published site.

The words come from two places, so they never have to be written into this public repository:
  .private-words            one per line, on your own computer (git ignores it)
  PRIVATE_WORDS             an environment variable, comma-separated: on GitHub, a repository secret of that name,
                            which the Pages workflow passes in before it publishes
The check reads every file in site/ and stops (exit 1) if any word appears, whatever the case.

  python3 tools/check_private.py
"""
import os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
words = [w.strip() for w in os.environ.get('PRIVATE_WORDS', '').split(',') if w.strip()]
pw = os.path.join(ROOT, '.private-words')
if os.path.exists(pw):
    words += [w.strip() for w in open(pw, encoding='utf-8') if w.strip() and not w.startswith('#')]
site = os.path.join(ROOT, 'site')
if not words:
    print('Private-word check: no words given (.private-words or PRIVATE_WORDS); nothing to check.')
    sys.exit(0)
found = []
for dirpath, _, files in os.walk(site):
    if os.path.relpath(dirpath, site).startswith('lib'):
        continue
    for fn in files:
        if not fn.endswith(('.html', '.json', '.txt', '.svg', '.js', '.css')):
            continue
        text = open(os.path.join(dirpath, fn), encoding='utf-8', errors='ignore').read()
        for w in words:
            if re.search(r'(?<![A-Za-z])' + re.escape(w) + r'(?![A-Za-z])', text, re.I):
                found.append((os.path.relpath(os.path.join(dirpath, fn), ROOT), w))
if found:
    for f, w in found:
        print(f'PRIVATE: "{w}" appears in {f}')
    sys.exit('Private-word check failed: nothing should be published until these are removed.')
print(f'Private-word check: none of {len(words)} private word(s) appear in site/.')
