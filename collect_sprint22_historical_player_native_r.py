"""Collect historical WNBA player boxes with an attribute-free native R export.

Legacy SportsDataverse tibbles can contain row metadata or column classes that make
ordinary CSV conversion produce empty identity fields. This collector strips every
column to plain character vectors in R before pandas reads the file.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

import collect_wehoop as base
from collect_wehoop_compatible import recover_canonical_columns

R_EXPORT = r'''
args <- commandArgs(trailingOnly = TRUE)
input_path <- args[[1]]
output_path <- args[[2]]
obj <- readRDS(input_path)

find_frames <- function(x) {
  frames <- list()
  walk <- function(value, path = "root") {
    if (is.data.frame(value)) frames[[length(frames) + 1L]] <<- value
    if (is.list(value) && !is.data.frame(value)) {
      nms <- names(value)
      for (i in seq_along(value)) {
        child <- if (!is.null(nms) && nzchar(nms[[i]])) nms[[i]] else as.character(i)
        walk(value[[i]], paste0(path, "/", child))
      }
    }
  }
  walk(x)
  frames
}

candidates <- if (is.data.frame(obj)) list(obj) else find_frames(obj)
if (length(candidates) == 0L) stop("No data-frame candidate found in RDS")

score_frame <- function(frame) {
  raw <- unclass(frame)
  lens <- vapply(raw, NROW, integer(1))
  rows <- if (length(lens)) max(lens, na.rm = TRUE) else 0L
  nms <- tolower(names(raw))
  identity <- sum(grepl("game_id|athlete_id|athlete_display_name|player", nms))
  as.numeric(rows) + identity * 1e7
}
frame <- candidates[[which.max(vapply(candidates, score_frame, numeric(1)))]]
raw <- unclass(frame)
if (length(raw) == 0L) stop("Selected player frame has no columns")

lens <- vapply(raw, NROW, integer(1))
positive <- lens[lens > 1L]
target <- if (length(positive)) {
  as.integer(names(sort(table(positive), decreasing = TRUE))[1])
} else {
  max(lens, na.rm = TRUE)
}
if (!is.finite(target) || target < 1L) stop("Could not determine row count")

flatten_one <- function(value) {
  if (length(value) == 0L || all(is.na(value))) return(NA_character_)
  paste(as.character(unlist(value, recursive = TRUE, use.names = FALSE)), collapse = "|")
}

clean <- list()
for (name in names(raw)) {
  column <- raw[[name]]
  n <- NROW(column)
  values <- NULL
  if (n == target) {
    if (is.list(column) && !is.data.frame(column)) {
      values <- vapply(column, flatten_one, character(1))
    } else {
      values <- as.character(column)
    }
  } else if (n == 1L) {
    value <- if (is.list(column)) flatten_one(column[[1]]) else as.character(column[[1]])
    values <- rep(value, target)
  } else if (n == 0L) {
    values <- rep(NA_character_, target)
  }
  if (!is.null(values)) {
    attributes(values) <- NULL
    clean[[name]] <- values
  }
}
if (length(clean) == 0L) stop("No rectangular columns survived")
rebuilt <- structure(clean, class = "data.frame", row.names = .set_row_names(target))
write.table(rebuilt, output_path, sep = ",", quote = TRUE, row.names = FALSE,
            col.names = TRUE, na = "", qmethod = "double", fileEncoding = "UTF-8")
'''


def decode_season(season: int) -> pd.DataFrame:
    url = base.SDV_URLS["player_box"].format(year=season)
    response = requests.get(url, headers=base.HEADERS, timeout=90, allow_redirects=True)
    if response.status_code == 404:
        raise RuntimeError(f"season {season}: player release not found")
    response.raise_for_status()

    rds_path = csv_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".rds", delete=False) as handle:
            handle.write(response.content)
            rds_path = handle.name
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as handle:
            csv_path = handle.name

        completed = subprocess.run(
            ["Rscript", "-e", R_EXPORT, rds_path, csv_path],
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"season {season}: native R export failed: {detail}")

        frame = pd.read_csv(csv_path, dtype=str, low_memory=False, keep_default_na=False)
        frame = recover_canonical_columns(frame, url)
        return frame
    finally:
        for path in (rds_path, csv_path):
            if path and os.path.exists(path):
                os.unlink(path)


def collect_season(season: int, out_dir: Path) -> dict:
    print(f"Season {season}: native R player export...", end="", flush=True)
    frame = decode_season(season)
    columns = [column for column in base.PLAYER_BOX_COLS if column in frame.columns]
    frame = frame[columns].copy()

    player_fields = [c for c in ("athlete_id", "athlete_display_name") if c in frame.columns]
    if "game_id" not in frame.columns or not player_fields:
        raise RuntimeError(f"season {season}: missing identity columns: {list(frame.columns)}")

    game_valid = frame["game_id"].astype(str).str.strip().ne("")
    player_valid = pd.Series(False, index=frame.index)
    for column in player_fields:
        player_valid |= frame[column].astype(str).str.strip().ne("")
    frame = frame[game_valid & player_valid].copy()
    if frame.empty:
        diagnostics = {
            "rows_before": int(len(game_valid)),
            "game_id_nonempty": int(game_valid.sum()),
            "player_identity_nonempty": int(player_valid.sum()),
        }
        raise RuntimeError(f"season {season}: no valid player rows; diagnostics={diagnostics}")

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"wehoop_player_box_{season}.csv"
    frame.to_csv(path, index=False)
    print(f" {len(frame)} rows -> {path}")
    return {"season": season, "rows": int(len(frame)), "path": str(path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--out", default=base.OUT_DIR)
    args = parser.parse_args()

    failures: list[str] = []
    results: list[dict] = []
    out_dir = Path(args.out)
    for season in range(args.start, args.end + 1):
        try:
            results.append(collect_season(season, out_dir))
        except Exception as exc:
            failures.append(f"{season}: {exc}")
            print(f" ERROR: {exc}")
    if failures:
        raise SystemExit("Historical native-R player collection failed:\n" + "\n".join(failures))
    print("Historical native-R player collection complete:", {
        "seasons": len(results),
        "rows": sum(item["rows"] for item in results),
    })


if __name__ == "__main__":
    main()
