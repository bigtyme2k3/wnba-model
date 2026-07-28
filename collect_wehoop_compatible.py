"""Run the WNBA collector with a native-R fallback for legacy RDS releases."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import pyreadr
import requests

import collect_wehoop as collector


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
            return frame
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

if (is.data.frame(obj)) {
  frame <- obj
} else if (is.list(obj)) {
  data_frames <- Filter(is.data.frame, obj)
  if (length(data_frames) == 0) {
    stop(sprintf("RDS object class %s contains no data frame", paste(class(obj), collapse=",")))
  }
  frame <- data_frames[[1]]
} else {
  frame <- tryCatch(as.data.frame(obj), error = function(e) NULL)
  if (is.null(frame)) {
    stop(sprintf("Unsupported RDS object class: %s", paste(class(obj), collapse=",")))
  }
}

write.csv(frame, output_path, row.names = FALSE, na = "")
'''
            completed = subprocess.run(
                [rscript, "-e", r_code, rds_path, csv_path],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()
                raise RuntimeError(f"native R failed to decode RDS: {detail}") from pyreadr_error

            frame = pd.read_csv(csv_path, low_memory=False)
            if frame.empty:
                raise RuntimeError("native R decoded the RDS but produced an empty table")
            return frame
    finally:
        for path in (rds_path, csv_path):
            if path and os.path.exists(path):
                os.unlink(path)


def main() -> None:
    collector.read_rds_url = read_rds_url_compatible
    collector.main()


if __name__ == "__main__":
    main()
