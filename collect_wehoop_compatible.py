"""Run the WNBA collector with a native-R fallback for legacy RDS releases."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

import pandas as pd
import pyreadr
import requests

import collect_wehoop as collector


COLUMN_ALIASES = {
    "team_home_away": "home_away",
    "total_rebounds": "rebounds",
    "total_turnovers": "turnovers",
    "athlete_name": "athlete_display_name",
    "player_name": "athlete_display_name",
    "player_id": "athlete_id",
    "team_abbrev": "team_abbreviation",
    "opponent_team_abbrev": "opponent_team_abbreviation",
}

EXPECTED_COLUMNS = sorted(
    set(collector.TEAM_BOX_COLS)
    | set(collector.PLAYER_BOX_COLS)
    | {
        "team_home_away", "total_rebounds", "total_turnovers",
        "team_display_name", "team_short_display_name", "team_score",
        "opponent_team_id", "opponent_team_name", "opponent_team_location",
        "opponent_team_display_name", "opponent_team_abbreviation",
        "opponent_team_score", "athlete_name", "player_name", "player_id",
    },
    key=len,
    reverse=True,
)


def clean_column(value: object) -> str:
    """Convert R/tibble/prefixed names to stable snake_case."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value))
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()


def recover_canonical_columns(frame: pd.DataFrame, url: str) -> pd.DataFrame:
    """Recover known box-score fields from prefixed legacy column names."""
    rename: dict[object, str] = {}
    used: set[str] = set()

    for original in frame.columns:
        cleaned = clean_column(original)
        match = None

        # Prefer the longest exact/suffix match so opponent_team_id does not
        # accidentally collapse into team_id.
        for expected in EXPECTED_COLUMNS:
            if cleaned == expected or cleaned.endswith("_" + expected):
                match = COLUMN_ALIASES.get(expected, expected)
                break

        if match and match not in used:
            rename[original] = match
            used.add(match)

    recovered = frame.rename(columns=rename)

    # Keep original columns for diagnostics, but validate that the essential
    # identity fields survived before the base collector applies its whitelist.
    if "player_boxscores" in url:
        has_player = any(
            column in recovered.columns
            for column in ("athlete_display_name", "athlete_id")
        )
        if "game_id" not in recovered.columns or not has_player:
            sample = [clean_column(c) for c in list(frame.columns)[:25]]
            raise RuntimeError(
                "legacy player table is missing canonical game/player identity "
                f"after column recovery; sample_columns={sample}"
            )
    elif "team_boxscores" in url and "game_id" not in recovered.columns:
        sample = [clean_column(c) for c in list(frame.columns)[:25]]
        raise RuntimeError(
            "legacy team table is missing canonical game_id after column recovery; "
            f"sample_columns={sample}"
        )

    return recovered


def read_rds_url_compatible(url: str) -> pd.DataFrame:
    """Download an RDS file, trying pyreadr first and native R second."""
    response = requests.get(
        url,
        headers=collector.HEADERS,
        timeout=60,
        allow_redirects=True,
    )
    if response.status_code == 404:
        return pd.DataFrame()
    response.raise_for_status()

    rds_path: str | None = None
    csv_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".rds", delete=False) as rds_file:
            rds_file.write(response.content)
            rds_path = rds_file.name

        try:
            result = pyreadr.read_r(rds_path)
            if not result:
                raise ValueError("pyreadr returned no objects")
            frame = next(iter(result.values()))
            print(" [pyreadr]", end="", flush=True)
            return recover_canonical_columns(frame, url)
        except Exception as pyreadr_error:
            rscript = shutil.which("Rscript")
            if not rscript:
                raise RuntimeError(
                    "pyreadr could not decode the RDS file and Rscript is unavailable"
                ) from pyreadr_error

            print(" [pyreadr unsupported; native R fallback]", end="", flush=True)
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as csv_file:
                csv_path = csv_file.name

            r_code = r'''
args <- commandArgs(trailingOnly = TRUE)
input_path <- args[[1]]
output_path <- args[[2]]
obj <- readRDS(input_path)

find_frame <- function(x) {
  candidates <- list()
  walk <- function(value) {
    if (is.data.frame(value)) candidates[[length(candidates) + 1L]] <<- value
    if (is.list(value) && !is.data.frame(value)) for (item in value) walk(item)
  }
  walk(x)
  if (length(candidates) == 0L) return(NULL)
  scores <- vapply(candidates, function(x) {
    raw <- unclass(x)
    lens <- vapply(raw, NROW, integer(1))
    rows <- if (length(lens) == 0L) 0L else max(lens, na.rm = TRUE)
    names_lower <- tolower(names(raw))
    identity <- sum(grepl("game|athlete|player|team|date", names_lower))
    as.numeric(rows) + identity * 1e6
  }, numeric(1))
  candidates[[which.max(scores)]]
}

frame <- if (is.data.frame(obj)) obj else find_frame(obj)
if (is.null(frame)) frame <- tryCatch(as.data.frame(obj), error = function(e) NULL)
if (is.null(frame)) stop(sprintf("Unsupported RDS object class: %s", paste(class(obj), collapse=",")))

raw <- unclass(frame)
if (length(raw) == 0L) stop("Decoded data frame has no columns")
lens <- vapply(raw, NROW, integer(1))
positive <- lens[lens > 1L]
target <- if (length(positive)) as.integer(names(sort(table(positive), decreasing = TRUE))[1]) else max(lens, na.rm = TRUE)
if (!is.finite(target) || target < 1L) stop("Unable to determine legacy table row count")

collapse_value <- function(value) {
  if (length(value) == 0L || all(is.na(value))) return(NA_character_)
  paste(as.character(unlist(value, recursive = TRUE, use.names = FALSE)), collapse = "|")
}

clean <- list()
dropped <- character()
for (name in names(raw)) {
  column <- raw[[name]]
  n <- NROW(column)
  if (n == 0L) {
    clean[[name]] <- rep(NA_character_, target)
  } else if (n == 1L && target > 1L) {
    value <- if (is.list(column)) collapse_value(column[[1]]) else column[[1]]
    clean[[name]] <- rep(value, target)
  } else if (n == target) {
    if (is.list(column) && !is.data.frame(column)) clean[[name]] <- vapply(column, collapse_value, character(1)) else clean[[name]] <- column
  } else {
    dropped <- c(dropped, sprintf("%s(%s)", name, n))
  }
}

if (length(clean) == 0L) stop("No rectangular columns survived legacy reconstruction")
rebuilt <- as.data.frame(clean, stringsAsFactors = FALSE, optional = TRUE, check.names = FALSE)
if (length(dropped)) warning(sprintf("Dropped irregular legacy columns: %s", paste(dropped, collapse = ", ")))
write.csv(rebuilt, output_path, row.names = FALSE, na = "")
'''
            completed = subprocess.run(
                [rscript, "-e", r_code, rds_path, csv_path],
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()
                raise RuntimeError(f"native R failed to decode RDS: {detail}") from pyreadr_error
            if completed.stderr.strip():
                print(f" [{completed.stderr.strip()}]", end="", flush=True)

            frame = pd.read_csv(csv_path, low_memory=False)
            if frame.empty:
                raise RuntimeError("native R decoded the RDS but produced an empty table")
            return recover_canonical_columns(frame, url)
    finally:
        for path in (rds_path, csv_path):
            if path and os.path.exists(path):
                os.unlink(path)


def main() -> None:
    collector.read_rds_url = read_rds_url_compatible
    collector.main()


if __name__ == "__main__":
    main()
