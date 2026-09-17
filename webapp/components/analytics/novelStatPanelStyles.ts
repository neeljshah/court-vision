// Scoped CSS for NovelStatPanel, kept out of the component to stay under the 300-line file rule.
export const NOVEL_STAT_PANEL_CSS = `
        .np{margin-top:28px;border:1px solid var(--rule-strong);border-top:3px solid var(--signal);
          border-radius:var(--radius-card);padding:22px 24px;max-width:680px;background:var(--paper-raised)}
        .np-top{display:flex;align-items:center;justify-content:space-between;gap:12px}
        .np h2{font-family:var(--font-display);font-weight:500;font-size:26px;letter-spacing:-.01em}
        .np-abbrev{margin-left:10px;font-size:12px;color:var(--ink-3);letter-spacing:.08em;vertical-align:middle}
        .np-null{font-size:10.5px;letter-spacing:.1em;color:var(--ink-3);border:1px solid var(--rule-strong);
          border-radius:var(--radius-chip);padding:3px 8px;white-space:nowrap}
        .np-headline{margin-top:10px;font-size:17px;line-height:1.55;color:var(--ink)}
        .np-window{margin-top:10px;font-size:12px;line-height:1.6;color:var(--ink-3);
          border-left:2px solid var(--rule-strong);padding-left:12px}
        .np-sec{margin-top:22px}
        .np-sec p{font-size:14.5px;line-height:1.6;color:var(--ink-2);margin-top:8px}
        .np-formula{margin-top:8px;background:var(--paper-tint);border:1px solid var(--rule);border-radius:8px;
          padding:12px 14px;font-size:12.5px;color:var(--ink);white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6}
        .np-gname{margin:0 0 6px;font-size:12px;letter-spacing:.08em;color:var(--signal-ink);text-transform:uppercase}
        .np-meta{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:11.5px;color:var(--ink-3);margin-bottom:8px}
        .np-meta b{color:var(--ink);font-weight:500;font-variant-numeric:tabular-nums}
        .np-scroll{overflow-x:auto;max-height:520px;overflow-y:auto;border:1px solid var(--rule);border-radius:8px}
        .np-scroll-hint{display:none}.np-table{border-collapse:collapse;width:100%;min-width:720px;font-size:12.5px}
        .np-table th{position:sticky;top:0;background:var(--paper-tint);text-align:left;font-weight:600;
          font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);
          padding:8px 12px;border-bottom:1px solid var(--rule-strong);white-space:nowrap}
        .np-table td{padding:7px 12px;border-bottom:1px solid var(--rule);color:var(--ink-2);
          vertical-align:top;line-height:1.45;max-width:340px;overflow-wrap:anywhere}
        .np-table tr:last-child td{border-bottom:0}
        .np-num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
        .np-pa-top{display:flex;align-items:center;gap:12px}
        .np-pa-lede{color:var(--ink-3);font-size:13.5px}
        .np-verdict{font-size:11px;letter-spacing:.08em;color:var(--signal-ink);
          border:1px solid var(--rule-strong);border-radius:var(--radius-chip);padding:2px 8px}
        .np-confounds{margin-top:22px;background:var(--paper-tint);border:1px solid var(--rule);
          border-left:3px solid var(--signal);border-radius:8px;padding:16px 18px}
        .np-confounds ul{margin:8px 0 0 18px}
        .np-confounds li{font-size:14px;line-height:1.55;color:var(--ink-2);margin-top:6px}
        .np-reasons{margin:0 0 0 18px}
        .np-reasons li{font-size:13.5px;line-height:1.5;color:var(--ink-2);margin-top:4px}
        .np-receipt{margin-top:20px;padding-top:14px;border-top:1px solid var(--rule);
          font-size:11px;color:var(--ink-3);line-height:1.7;word-break:break-all}
        @media(max-width:720px){.np-scroll-hint{display:block;margin:8px 0 0;font-family:var(--font-mono);font-size:12px;color:var(--ink-3)}}
      `;
