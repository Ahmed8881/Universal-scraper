from __future__ import annotations

from typing import Dict, List
import pandas as pd

EXPORT_COLUMNS = [
    "name",
    "website",
    "email",
    "phone",
    "address",
    "socials",
    "source",
    "score",
    "status",
    "notes",
]


def export_to_csv(rows: List[Dict[str, str]], path: str) -> None:
    df = pd.DataFrame(rows)
    for col in EXPORT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[EXPORT_COLUMNS]
    df.to_csv(path, index=False, encoding="utf-8-sig")


def export_to_excel(rows: List[Dict[str, str]], path: str) -> None:
    df = pd.DataFrame(rows)
    for col in EXPORT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[EXPORT_COLUMNS]
    df.to_excel(path, index=False)


def export_selected(treeview, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    selected = []
    for item in treeview.selection():
        values = treeview.item(item, "values")
        # Map the columns by our table order in the UI
        row = {
            "name": values[0],
            "website": values[1],
            "email": values[2],
            "phone": values[3],
            "address": values[4],
            "socials": values[5] if len(values) > 5 else "",
        }
        # backfill extra fields if available in full row store
        for r in rows:
            if r.get("name") == row["name"] and r.get("website") == row["website"]:
                row.update({
                    "source": r.get("source", ""),
                    "score": r.get("score", ""),
                    "status": r.get("status", ""),
                    "notes": r.get("notes", ""),
                })
                break
        selected.append(row)
    return selected
