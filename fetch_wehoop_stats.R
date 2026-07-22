#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(wehoop)
  library(dplyr)
  library(readr)
  library(jsonlite)
  library(lubridate)
})

args <- commandArgs(trailingOnly = TRUE)
arg_value <- function(name, default = NULL) {
  i <- match(name, args)
  if (!is.na(i) && i < length(args)) args[[i + 1]] else default
}

target <- arg_value("--date", format(Sys.Date(), "%Y-%m-%d"))
out_dir <- arg_value("--out", "data/raw")
season <- as.integer(substr(target, 1, 4))
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

message("=== WEHOOP WNBA STATS ===")
message("Target date: ", target)
message("Season: ", season)

safe_scoreboard <- function() {
  x <- tryCatch(espn_wnba_scoreboard(season), error = function(e) NULL)
  if (!is.null(x) && is.data.frame(x) && nrow(x) > 0) return(x)

  dates <- seq(as.Date(target) - 45, as.Date(target), by = "day")
  parts <- lapply(dates, function(d) {
    tryCatch(espn_wnba_scoreboard(format(d, "%Y%m%d")), error = function(e) NULL)
  })
  bind_rows(Filter(function(x) !is.null(x) && is.data.frame(x) && nrow(x) > 0, parts))
}

schedule <- safe_scoreboard()
if (is.null(schedule) || !is.data.frame(schedule) || nrow(schedule) == 0) {
  stop("wehoop returned no WNBA schedule rows")
}

schedule <- schedule %>%
  mutate(game_id = as.character(game_id), game_date = as.Date(game_date)) %>%
  filter(game_date <= as.Date(target)) %>%
  distinct(game_id, .keep_all = TRUE)

final_mask <- grepl("FINAL", toupper(as.character(schedule$status_name))) |
  (!is.na(schedule$home_score) & !is.na(schedule$away_score) & schedule$game_date < as.Date(target))
completed <- schedule[final_mask, , drop = FALSE]

cache_path <- file.path(out_dir, "wehoop_player_boxscores.csv")
existing <- if (file.exists(cache_path)) suppressMessages(read_csv(cache_path, show_col_types = FALSE)) else tibble()
known <- if (nrow(existing)) unique(as.character(existing$game_id)) else character()
missing_ids <- setdiff(as.character(completed$game_id), known)
message("Completed games: ", nrow(completed), " | cached: ", length(known), " | new: ", length(missing_ids))

# ESPN/wehoop occasionally changes a field type between games (for example,
# numeric values in one response and text such as "--" in another). Coerce raw
# provider frames to character before bind_rows; the normalized output below
# then applies the canonical numeric/date types explicitly.
raw_as_character <- function(x) {
  if (is.null(x) || !is.data.frame(x)) return(tibble())
  as_tibble(x) %>% mutate(across(everything(), as.character))
}

new_boxes <- list()
skipped_ids <- character()
failed_ids <- character()
for (gid in missing_ids) {
  message("Fetching player boxscore: ", gid)
  box <- tryCatch(
    espn_wnba_player_box(gid),
    error = function(e) {
      warning("wehoop player box failed for ", gid, ": ", conditionMessage(e))
      failed_ids <<- c(failed_ids, gid)
      NULL
    }
  )

  has_rows <- !is.null(box) && is.data.frame(box) && length(nrow(box)) == 1 && !is.na(nrow(box)) && nrow(box) > 0
  if (isTRUE(has_rows)) {
    new_boxes[[length(new_boxes) + 1]] <- raw_as_character(box)
  } else {
    skipped_ids <- c(skipped_ids, gid)
    message("Skipping unavailable player boxscore: ", gid)
  }
  Sys.sleep(0.15)
}

existing <- raw_as_character(existing)
fresh_boxes <- if (length(new_boxes)) bind_rows(new_boxes) else tibble()
all_boxes <- bind_rows(existing, fresh_boxes)
if (nrow(all_boxes) == 0) stop("No wehoop player boxscore rows are available")

all_boxes <- all_boxes %>%
  mutate(game_id = as.character(game_id), game_date = as.Date(game_date)) %>%
  distinct(game_id, athlete_id, .keep_all = TRUE) %>%
  arrange(game_date, game_id, athlete_display_name)
write_csv(all_boxes, cache_path, na = "")

num <- function(x) suppressWarnings(as.numeric(na_if(trimws(as.character(x)), "")))
normalized <- all_boxes %>%
  transmute(
    game_id = as.character(game_id),
    game_date = as.character(as.Date(game_date)),
    team = coalesce(as.character(team_display_name), as.character(team_name)),
    player = as.character(athlete_display_name),
    position = as.character(athlete_position_abbreviation),
    minutes = num(minutes),
    fgm = num(field_goals_made),
    fga = num(field_goals_attempted),
    threes = num(three_point_field_goals_made),
    fta = num(free_throws_attempted),
    ftm = num(free_throws_made),
    reb = num(rebounds),
    ast = num(assists),
    stl = num(steals),
    blk = num(blocks),
    tov = num(turnovers),
    pf = num(fouls),
    pts = num(points),
    opponent = as.character(opponent_team_display_name),
    opponent_abbr = as.character(opponent_team_abbreviation),
    team_abbr = as.character(team_abbreviation),
    team_logo = as.character(team_logo),
    source = "wehoop_espn"
  )
write_csv(normalized, file.path(out_dir, "boxscores_wehoop.csv"), na = "")

latest_date <- max(normalized$game_date, na.rm = TRUE)
write_csv(normalized %>% filter(game_date == latest_date), file.path(out_dir, paste0("boxscores_", latest_date, ".csv")), na = "")

safe_mean <- function(x) round(mean(num(x), na.rm = TRUE), 3)
players <- normalized %>%
  filter(!is.na(player), player != "") %>%
  group_by(player) %>%
  arrange(desc(game_date), .by_group = TRUE) %>%
  group_modify(function(.x, .y) {
    l5 <- head(.x, 5)
    tibble(
      team = first(na.omit(.x$team)),
      pos = first(na.omit(.x$position)),
      gp = n_distinct(.x$game_id),
      ppg = safe_mean(.x$pts),
      mpg = safe_mean(.x$minutes),
      reb = safe_mean(.x$reb),
      ast = safe_mean(.x$ast),
      roll5_pts = safe_mean(l5$pts),
      roll5_reb = safe_mean(l5$reb),
      roll5_ast = safe_mean(l5$ast),
      roll5_mpg = safe_mean(l5$minutes),
      roll5_threes = safe_mean(l5$threes),
      roll5_gp = n_distinct(l5$game_id),
      team_abbr = first(na.omit(.x$team_abbr)),
      team_logo = first(na.omit(.x$team_logo))
    )
  }) %>%
  ungroup()

player_list <- setNames(lapply(seq_len(nrow(players)), function(i) {
  r <- players[i, ]
  list(
    player = r$player,
    team = r$team,
    pos = r$pos,
    gp = r$gp,
    ppg = r$ppg,
    mpg = r$mpg,
    usage = NULL,
    ts = NULL,
    ts_pct = NULL,
    reb = r$reb,
    ast = r$ast,
    roll5_pts = r$roll5_pts,
    roll5_reb = r$roll5_reb,
    roll5_ast = r$roll5_ast,
    roll5_mpg = r$roll5_mpg,
    roll5_threes = r$roll5_threes,
    roll5_gp = r$roll5_gp,
    recent_source = "wehoop ESPN player boxscores",
    team_abbr = r$team_abbr,
    team_logo = r$team_logo,
    net_rating = NULL,
    pace = NULL,
    team_ortg = NULL,
    team_drtg = NULL,
    team_pace = NULL,
    opp_pts_allowed_team = NULL,
    source = "wehoop_espn",
    updated_at = format(Sys.time(), tz = "UTC", usetz = TRUE)
  )
}), players$player)
write_json(player_list, file.path(out_dir, "wnba_players_live.json"), pretty = TRUE, auto_unbox = TRUE, na = "null")

status <- list(
  status = "ok",
  provider = "sportsdataverse/wehoop",
  upstream = "ESPN",
  target_date = target,
  season = season,
  completed_games = nrow(completed),
  player_game_rows = nrow(normalized),
  players = nrow(players),
  latest_game_date = latest_date,
  requested_new_games = length(missing_ids),
  new_games_fetched = length(new_boxes),
  skipped_unavailable_games = length(unique(skipped_ids)),
  skipped_game_ids = unique(skipped_ids),
  fetch_error_games = length(unique(failed_ids)),
  fetch_error_game_ids = unique(failed_ids),
  generated_at_utc = format(Sys.time(), tz = "UTC", usetz = TRUE)
)
write_json(status, file.path(out_dir, "wehoop_stats_status.json"), pretty = TRUE, auto_unbox = TRUE)
message(
  "✓ wehoop stats complete: ", nrow(normalized), " player-game rows, ", nrow(players),
  " players | fetched: ", length(new_boxes), " | skipped: ", length(unique(skipped_ids)),
  " | errors: ", length(unique(failed_ids))
)
