# Recognition evaluation

Use Attendly's **Research Evaluation** page to record a controlled observation for each trial. Include the expected identity for enrolled participants, the predicted identity returned by Attendly (blank when rejected), environmental condition, lighting, distance, orientation, decision, and measured elapsed time. Use consented participants and do not upload identifying photos or biometric templates to the exported results.

Export the actual trial history from the page or run the summarizer against that CSV:

```powershell
python research/evaluate_results.py path\to\research-trials.csv
```

The summary protocol uses identification trials only. For a known identity, exact expected/predicted match is TP; rejection or wrong identity is FN. For an unknown person, rejection is TN and any accepted identity is FP. Accuracy denominator is all identification trials; precision uses TP+FP; recall uses TP+FN; FAR uses FP+TN; FRR uses FN+TP. Zero denominators are shown as N/A. The console report groups by the recorded condition and includes average/minimum/maximum processing time. Verification trials are excluded and require a separately designed genuine/impostor threshold protocol.

The included `evaluation_template.csv` is header-only. It contains no measurements. Gather an adequate, balanced sample across conditions before making claims; results from a small convenience sample are exploratory and hardware-specific.
