"""Inspect one legacy SportsDataverse WNBA player RDS without mutating warehouse data."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import requests

BASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_wnba_player_boxscores/player_box_{season}.rds"
HEADERS = {"User-Agent": "Mozilla/5.0 (research project)"}

R_CODE = r'''
args <- commandArgs(trailingOnly=TRUE)
input <- args[[1]]
output <- args[[2]]
season <- as.integer(args[[3]])
obj <- readRDS(input)
items <- list()
walk <- function(x, path="root", depth=0L) {
  cls <- paste(class(x), collapse="|")
  dims <- if (is.data.frame(x)) c(nrow(x), ncol(x)) else c(NA_integer_, NA_integer_)
  cols <- if (is.data.frame(x)) names(x) else character()
  items[[length(items)+1L]] <<- list(
    path=path, depth=depth, class=cls,
    rows=ifelse(is.na(dims[1]), NULL, dims[1]),
    columns=ifelse(is.na(dims[2]), NULL, dims[2]),
    column_names=cols
  )
  if (is.list(x) && !is.data.frame(x) && depth < 8L) {
    nms <- names(x)
    for (i in seq_along(x)) {
      label <- if (!is.null(nms) && nzchar(nms[[i]])) nms[[i]] else paste0("item_", i)
      walk(x[[i]], paste0(path, "/", label), depth+1L)
    }
  }
}
walk(obj)
frames <- Filter(function(z) !is.null(z$rows), items)
score <- function(z) {
  n <- tolower(z$column_names)
  identity <- sum(grepl("game|player|athlete|team|date", n))
  as.numeric(z$rows) + identity * 1e6
}
best <- if (length(frames)) frames[[which.max(vapply(frames, score, numeric(1)))]] else NULL
payload <- list(
  season=season,
  root_class=paste(class(obj), collapse="|"),
  object_count=length(items),
  data_frame_count=length(frames),
  best_candidate=best,
  objects=items
)
jsonlite::write_json(payload, output, pretty=TRUE, auto_unbox=TRUE, null="null")
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2023)
    parser.add_argument("--out", default="data/diagnostics/legacy_player_schema_2023.json")
    args = parser.parse_args()

    out = Path(args.out.replace("2023", str(args.season)))
    out.parent.mkdir(parents=True, exist_ok=True)
    url = BASE.format(season=args.season)
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".rds") as rds:
        rds.write(response.content)
        rds.flush()
        completed = subprocess.run(
            ["Rscript", "-e", R_CODE, rds.name, str(out), str(args.season)],
            text=True,
            capture_output=True,
            timeout=180,
        )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)

    report = json.loads(out.read_text())
    print(json.dumps({
        "season": report["season"],
        "root_class": report["root_class"],
        "object_count": report["object_count"],
        "data_frame_count": report["data_frame_count"],
        "best_candidate": report.get("best_candidate"),
        "report_path": str(out),
    }, indent=2))


if __name__ == "__main__":
    main()
