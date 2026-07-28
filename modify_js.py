import re

def modify():
    with open('static/main.js', 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Inject isStaticMode at the top
    if 'let isStaticMode =' not in content:
        content = "const isStaticMode = window.location.hostname.includes('github.io') || window.location.hostname.includes('githubusercontent.com');\n" + content
        
    # Rewrite fetchHistoryDates
    history_dates_old = """async function fetchHistoryDates() {
    try {
        const res = await fetch('/api/history-dates');
        const dates = await res.json();
        
        historySelect.innerHTML = '<option value="LATEST">最新結果 (Live Scan)</option>';
        
        dates.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d;
            opt.innerText = d;
            historySelect.appendChild(opt);
        });
    } catch (e) {
        console.error("Failed to fetch scan history dates", e);
    }
}"""

    history_dates_new = """async function fetchHistoryDates() {
    try {
        if (isStaticMode) {
            historySelect.innerHTML = '<option value="LATEST">最新結果 (Static)</option>';
            return;
        }
        const res = await fetch('/api/history-dates');
        const dates = await res.json();
        
        historySelect.innerHTML = '<option value="LATEST">最新結果 (Live Scan)</option>';
        
        dates.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d;
            opt.innerText = d;
            historySelect.appendChild(opt);
        });
    } catch (e) {
        console.error("Failed to fetch scan history dates", e);
    }
}"""
    # Wait, the exact string in main.js might have CP950/Big5 encoded characters if read wrongly, or just different formatting.
    # Let's use regex.
    content = re.sub(r'async function fetchHistoryDates\(\) \{\s*try \{', 
                     r'async function fetchHistoryDates() {\n    try {\n        if (isStaticMode) {\n            historySelect.innerHTML = \'<option value="LATEST">最新結果 (Static Mode)</option>\';\n            return;\n        }', 
                     content)
                     
    content = re.sub(r'async function loadHistoricalScan\(\) \{\s*const val = historySelect.value;\s*if \(val === \'LATEST\'\) \{',
                     r'async function loadHistoricalScan() {\n    const val = historySelect.value;\n    if (val === \'LATEST\') {\n        if (isStaticMode) {\n            try {\n                const res = await fetch(\'./latest_scan.json\');\n                if (res.ok) {\n                    const data = await res.json();\n                    scanResults = data.results;\n                    applyFilters();\n                    lastScanTime.innerText = "掃描時間: " + data.date;\n                    return;\n                }\n            } catch(e) {}\n        }',
                     content)
                     
    content = re.sub(r'async function loadHistorySummary\(\) \{\s*try \{\s*const res = await fetch\(\'/api/history-summary\'\);',
                     r'async function loadHistorySummary() {\n    try {\n        let res;\n        if (isStaticMode) {\n            res = await fetch(\'./history_summary.json\');\n        } else {\n            res = await fetch(\'/api/history-summary\');\n        }',
                     content)

    with open('static/main.js', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("main.js updated for static mode.")

modify()
