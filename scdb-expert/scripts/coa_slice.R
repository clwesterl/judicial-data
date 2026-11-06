# coa_slice.R -- extract the SCDB-crosswalk slice of the Comprehensive Court of
# Appeals Database (Sapiro-Gheiler & Kastellec, Release 09-2026).
#
# Run from this folder, in Terminal:
#     cd ~/Desktop/coa\ data
#     Rscript coa_slice.R
#
# The RData is uncompressed, so load() needs roughly 6-8 GB of RAM and a few
# minutes.  Writes three gzipped CSVs beside the data:
#     coa_columns.csv.gz        all 809 columns: type, width, missing count, example
#     coa_link.csv.gz           all 512,263 cases, crosswalk + judge/panel columns
#     coa_scotus_bridge.csv.gz  the Songer-coded cases the Supreme Court reviewed

t0  <- Sys.time()
say <- function(...) { cat(..., "\n", sep = ""); flush.console() }

say("loading ccad_09-2026.RData  (512,263 rows x 809 columns) ...")
env <- new.env()
load("ccad_09-2026.RData", envir = env)
nm <- ls(env)
df <- NULL
for (n in nm) if (is.data.frame(get(n, envir = env))) { df <- get(n, envir = env); break }
if (is.null(df)) stop("no data frame in the RData; objects found: ", paste(nm, collapse = ", "))
rm(env); invisible(gc())
say(sprintf("loaded '%s': %d rows x %d columns  (%.1f min)",
            n, nrow(df), ncol(df), as.numeric(difftime(Sys.time(), t0, units = "mins"))))

## ---- 1. full column inventory --------------------------------------------
probe  <- df[seq_len(min(3000L, nrow(df))), , drop = FALSE]
widths <- vapply(probe, function(x)
            if (is.character(x)) max(c(0L, nchar(x)), na.rm = TRUE) else 0L, integer(1))
first_val <- function(x) {
  v <- x[!is.na(x)]
  if (!length(v)) "" else substr(gsub("[\r\n\t]+", " ", as.character(v[1])), 1, 100)
}
write.csv(data.frame(position  = seq_along(df),
                     column    = names(df),
                     type      = vapply(df, function(x) class(x)[1], character(1)),
                     max_chars = as.integer(widths),
                     n_missing = vapply(df, function(x) sum(is.na(x)), numeric(1)),
                     example   = vapply(probe, first_val, character(1)),
                     row.names = NULL, stringsAsFactors = FALSE),
          gzfile("coa_columns.csv.gz"), row.names = FALSE)
say("wrote coa_columns.csv.gz  (", ncol(df), " columns documented)")

## ---- 2. the crosswalk and analysis columns --------------------------------
want <- c(
  # CoA case identity and structure
  "caseid", "source", "citation", "cite_count", "circuit", "year", "decision_date",
  "docket_number", "judge_count", "is_enbanc", "is_percuriam",
  "n_opinions", "n_majority", "n_concurrence", "n_dissent", "author",
  "all_judges_matched", "all_authors_matched",
  # LLM SCDB-track parties and substance (also the fuzzy-match payload)
  "scdb_first_appellant_name", "scdb_first_appellant_category",
  "scdb_first_respondent_name", "scdb_first_respondent_category",
  "scdb_first_appealed", "scdb_first_disposition", "scdb_first_appellant_win",
  "scdb_first_broad_area", "scdb_second_sub_area",
  "scdb_first_direction_oneshot", "scdb_second_direction_mech",
  # Opinion author, first dissenter, first concurrer: identity and ideology
  "author_id", "author_name", "author_dem", "author_appointing_president",
  "author_ghp", "author_age", "author_tenure", "author_senior", "author_fem",
  "author_nonwhite", "author_is_appellate",
  "dis1_id", "dis1_name", "dis1_dem", "dis1_ghp",
  "conc1_id", "conc1_name", "conc1_dem", "conc1_ghp",
  # Panel roster and panel-level aggregates
  "j1_id", "j1_name", "j1_dem", "j1_ghp", "j1_appointing_president",
  "j2_id", "j2_name", "j2_dem", "j2_ghp",
  "j3_id", "j3_name", "j3_dem", "j3_ghp",
  "enbanc_id", "enbanc_name",
  "num_dems", "num_women", "num_nonwhite", "mixed_panel",
  "ghp_min", "ghp_max", "ghp_med", "ghp_mean", "age_med", "tenure_med",
  # Songer ground truth: the SCOTUS-review flag and its citation keys
  "songer_present", "songer_gt_supct", "songer_gt_phase", "songer_gt_sample",
  "songer_gt_cite", "songer_gt_vol", "songer_gt_beginpg", "songer_gt_endpage",
  "songer_gt_year", "songer_gt_month", "songer_gt_day", "songer_gt_decisiondate",
  "songer_gt_circuit", "songer_gt_docnum", "songer_gt_docknum", "songer_gt_casenum",
  "songer_gt_fileid", "songer_gt_treat", "songer_gt_direct1", "songer_gt_majvotes",
  "songer_gt_unan", "songer_gt_appel1", "songer_gt_respond1",
  "songer_gt_genapel1", "songer_gt_genresp1", "songer_gt_origin",
  "songer_gt_applfrom", "songer_gt_state", "songer_gt_district",
  # FJC Integrated Database keys
  "idb_present", "idb_circuit", "idb_docket", "idb_dktdate", "idb_ddocket",
  "idb_ddist", "idb_appdate", "idb_judgdate", "idb_disp", "idb_outcome",
  "idb_opdisp", "idb_match_stage")

cols <- intersect(want, names(df))
miss <- setdiff(want, names(df))
if (length(miss)) say("NOT FOUND (check coa_columns.csv.gz): ", paste(miss, collapse = ", "))
say("writing ", length(cols), " crosswalk columns")

write.csv(df[, cols, drop = FALSE], gzfile("coa_link.csv.gz"), row.names = FALSE)
say("wrote coa_link.csv.gz  (", nrow(df), " rows x ", length(cols), " columns)")

## ---- 3. the SCOTUS-review validation set ---------------------------------
if ("songer_gt_supct" %in% names(df)) {
  v   <- df$songer_gt_supct
  say("songer_gt_supct values: ",
      paste(sprintf("%s=%d", names(table(v)), table(v)), collapse = "  "),
      "   (NA: ", sum(is.na(v)), ")")
  hit <- !is.na(v) & v == 1
  if (any(hit)) {
    write.csv(df[hit, cols, drop = FALSE], gzfile("coa_scotus_bridge.csv.gz"), row.names = FALSE)
    say("wrote coa_scotus_bridge.csv.gz  (", sum(hit), " rows)")
  } else say("no rows with songer_gt_supct == 1")
} else say("songer_gt_supct not present")

for (f in c("coa_columns.csv.gz", "coa_link.csv.gz", "coa_scotus_bridge.csv.gz"))
  if (file.exists(f)) say(sprintf("  %-28s %7.1f MB", f, file.size(f) / 1e6))
say(sprintf("done in %.1f min", as.numeric(difftime(Sys.time(), t0, units = "mins"))))
