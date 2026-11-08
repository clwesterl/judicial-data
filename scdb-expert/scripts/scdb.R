# scdb.R -- R helpers for the combined Supreme Court Database (1791-present).
# Base R only; uses readr for faster reading if it is installed.
# NOTE: written to mirror scripts/scdb.py but not executed in the environment that
# built this skill (no R there). Sanity-check on first use: nrow(scdb_load()) == 29270.
#
#   source("~/.claude/skills/scdb-expert/scripts/scdb.R")   # or wherever the skill lives
#   cases <- scdb_load("case")
#   votes <- scdb_load("justice")                  # drops the 25 legacy placeholder rows
#   cases <- scdb_label(cases, c("issueArea", "decisionDirection"))   # adds *_label columns
#   cases$issueArea_f <- scdb_factor(cases$issueArea, "issueArea")    # labeled factor for models
#   scdb_find(cases, "384 U.S. 436")
#   mv <- scdb_merits_votes(scdb_formally_decided(votes))
#   votes <- scdb_add_jcs(votes)                   # Judicial Common Space score by justice-term
#   cases <- scdb_add_medians(cases)               # SC / House / Senate / president medians by term
#   coa   <- scdb_jcs("coa")                       # courts of appeals judges' JCS scores

scdb_dir <- function() {
  cands <- c(Sys.getenv("SCDB_SKILL_DIR"),
             file.path(path.expand("~"), ".claude", "skills", "scdb-expert"),
             "/mnt/skills/user/scdb-expert", "/mnt/skills/plugins/scdb-expert")
  for (d in cands) {
    if (nzchar(d) && file.exists(file.path(d, "data", "MANIFEST.json"))) return(d)
  }
  stop("Can't locate the scdb-expert skill folder; set Sys.setenv(SCDB_SKILL_DIR = '...')")
}

.scdb_text  <- c("caseId", "docketId", "caseIssuesId", "voteId", "usCite", "sctCite", "ledCite",
                 "lexisCite", "chief", "docket", "caseName", "lawMinor", "justiceName")
.scdb_dates <- c("dateDecision", "dateArgument", "dateRearg")

scdb_load <- function(level = c("case", "justice"), keep_placeholders = FALSE, dir = scdb_dir()) {
  level <- match.arg(level)
  f <- file.path(dir, "data", if (level == "case") "case_citation.csv.gz" else "justice_citation.csv.gz")
  if (requireNamespace("readr", quietly = TRUE)) {
    df <- as.data.frame(readr::read_csv(f, col_types = readr::cols(.default = "c"), na = "",
                                        progress = FALSE))
  } else {
    df <- utils::read.csv(f, colClasses = "character", na.strings = "", encoding = "UTF-8",
                          check.names = FALSE)
  }
  if (level == "justice" && !keep_placeholders) df <- df[df$justice != "-99", , drop = FALSE]
  for (col in names(df)) {
    if (col %in% .scdb_dates) {
      df[[col]] <- as.Date(df[[col]], format = "%m/%d/%Y")
    } else if (!(col %in% .scdb_text)) {
      df[[col]] <- as.integer(df[[col]])
    }
  }
  rownames(df) <- NULL
  df
}

# default samples (see references/analysis_guide.md section 1)
scdb_formally_decided <- function(df, include_equally_divided = FALSE) {
  df[df$decisionType %in% c(1L, 6L, 7L, if (include_equally_divided) 5L), , drop = FALSE]
}
scdb_merits_votes <- function(v) v[v$vote %in% 1:5, , drop = FALSE]

scdb_value_labels <- function(dir = scdb_dir()) {
  utils::read.csv(file.path(dir, "references", "value_labels.csv"),
                  colClasses = c("character", "integer", "character", "character"),
                  encoding = "UTF-8")
}

scdb_labels <- function(variable, dir = scdb_dir()) {
  vl <- scdb_value_labels(dir)
  x <- vl[vl$variable == variable, ]
  if (nrow(x) == 0) stop("no value labels for ", variable)
  stats::setNames(x$label, x$code)
}

scdb_label <- function(df, vars = NULL, dir = scdb_dir()) {
  vl <- scdb_value_labels(dir)
  if (is.null(vars)) vars <- intersect(names(df), unique(vl$variable))
  for (v in vars) {
    m <- vl[vl$variable == v, ]
    df[[paste0(v, "_label")]] <- m$label[match(as.integer(df[[v]]), m$code)]
  }
  df
}

scdb_factor <- function(x, variable, dir = scdb_dir()) {
  lab <- scdb_labels(variable, dir)
  factor(as.integer(x), levels = as.integer(names(lab)), labels = unname(lab))
}

scdb_find <- function(df, query) {
  key <- function(s) gsub("[[:space:].]", "", tolower(s))
  q <- trimws(query)
  if (grepl("^[0-9]{4}-[0-9]{3}$", q)) return(df[df$caseId == q, , drop = FALSE])
  hit <- rep(FALSE, nrow(df))
  for (col in c("usCite", "sctCite", "ledCite", "lexisCite")) {
    hit <- hit | (!is.na(df[[col]]) & key(df[[col]]) == key(q))
  }
  if (any(hit)) return(df[hit, , drop = FALSE])
  nm <- tolower(gsub("[\u2018\u2019]", "'", df$caseName))
  df[grepl(tolower(q), nm, fixed = TRUE), , drop = FALSE]
}

# ---- Judicial Common Space (see references/jcs.md)
scdb_jcs <- function(which = c("justice", "coa", "medians", "circuits", "circuit_medians"),
                     dir = scdb_dir()) {
  which <- match.arg(which)
  rd <- function(f) utils::read.csv(file.path(dir, "data", "jcs", f), encoding = "UTF-8",
                                    stringsAsFactors = FALSE)
  if (which == "circuit_medians") {
    m <- rd("jcs_medians.csv"); circ <- rd("circuits.csv")
    out <- do.call(rbind, lapply(circ$circuit, function(k)
      data.frame(year = m$year, term = m$term, circuit = k,
                 median = m[[paste0("circuit_median", k)]], sd = m[[paste0("circuit_sd", k)]])))
    out <- merge(out, circ[, c("circuit", "circuit_name", "scdb_caseSource")], by = "circuit")
    out <- out[!is.na(out$median), ]
    out <- out[!duplicated(out[, c("year", "circuit", "median", "sd")]), ]   # 1924 appears twice
    return(out[order(out$circuit, out$year), ])
  }
  rd(switch(which, justice = "jcs_justice_term.csv", coa = "jcs_coa_judges.csv",
            medians = "jcs_medians.csv", circuits = "circuits.csv"))
}

scdb_add_jcs <- function(v, dir = scdb_dir()) {
  j <- scdb_jcs("justice", dir)[, c("term", "justice", "jcs")]
  merge(v, j, by = c("term", "justice"), all.x = TRUE, sort = FALSE)
}

# medians row for term t is calendar year t + 1
scdb_add_medians <- function(df, cols = c("sc_median", "president", "house_median", "senate_median"),
                             dir = scdb_dir()) {
  m <- scdb_jcs("medians", dir)
  m <- m[!is.na(m$term), c("term", cols)]
  merge(df, m, by = "term", all.x = TRUE, sort = FALSE)
}

# ---- Comprehensive Court of Appeals Database (see references/coa.md)
# Circuit numbering in these tables is the CCAD's: 0 = D.C., 1-11 by number,
# 12 = Federal. scdb_jcs("circuits") crosswalks it to the JCS and SCDB schemes.
scdb_coa <- function(which = c("cases", "crosswalk"), dir = scdb_dir()) {
  which <- match.arg(which)
  f <- file.path(dir, "data", "coa",
                 switch(which, cases = "coa_cases.csv.gz", crosswalk = "crosswalk.csv.gz"))
  d <- if (requireNamespace("readr", quietly = TRUE)) {
    as.data.frame(readr::read_csv(f, col_types = readr::cols(
      caseid = readr::col_character(), coa_caseid = readr::col_character(),
      citation = readr::col_character(), coa_citation = readr::col_character(),
      docket_number = readr::col_character()), progress = FALSE))
  } else {
    utils::read.csv(gzfile(f), encoding = "UTF-8", stringsAsFactors = FALSE,
                    colClasses = c(caseid = "character", coa_caseid = "character"))
  }
  for (k in intersect(c("decision_date", "coa_date", "scotus_date"), names(d)))
    d[[k]] <- as.Date(d[[k]])
  d
}

# Attach the reviewed courts-of-appeals case to SCDB case rows. Links are fuzzy --
# neither database carries the other's citation -- so pick a confidence tier:
#   "A" mutual best match, score >= 0.50  (~1.2% false-positive rate)
#   "B" mutual best match, score >= 0.35  (~1.8% cumulative)
#   "C" score >= 0.20                     (inspect before using)
scdb_add_coa <- function(c, confidence = "A", dir = scdb_dir()) {
  x <- scdb_coa("crosswalk", dir)
  x <- x[x$confidence %in% confidence, ]
  keep <- c("caseId", "coa_caseid", "coa_citation", "coa_date", "gap_days", "score", "confidence")
  x <- x[, keep]
  names(x) <- c("caseId", "coa_caseid", "coa_citation", "coa_date", "coa_gap_days",
                "coa_match_score", "coa_match_confidence")
  merge(c, x, by = "caseId", all.x = TRUE, sort = FALSE)
}

# The reverse: attach the reviewing Supreme Court case to CCAD rows.
scdb_add_scdb <- function(d, confidence = "A", dir = scdb_dir()) {
  x <- scdb_coa("crosswalk", dir)
  x <- x[x$confidence %in% confidence,
         c("coa_caseid", "caseId", "caseName", "usCite", "term", "scotus_date",
           "gap_days", "score", "confidence")]
  names(x)[1] <- "caseid"
  names(x)[names(x) == "score"] <- "match_score"
  names(x)[names(x) == "confidence"] <- "match_confidence"
  merge(d, x, by = "caseid", all.x = TRUE, sort = FALSE)
}

# The CCAD's disposition columns are documented as using "the SCDB scheme", but the
# numbering differs: codes 1-8 sit one below SCDB's and 9/0 wrap around. Remap before
# comparing with SCDB caseDisposition / lcDisposition.
scdb_coa_disposition <- function(x) {
  m <- c(`0` = 11L, `1` = 2L, `2` = 3L, `3` = 4L, `4` = 5L,
         `5` = 6L, `6` = 7L, `7` = 8L, `8` = 9L, `9` = 1L, `10` = 10L)
  unname(m[as.character(x)])
}

# For the reproduced songer_gt_* direction fields ONLY (0 = not ascertained,
# 1 = conservative, 2 = mixed, 3 = liberal); mixed collapses into SCDB's 3.
# The CCAD's own LLM-coded direction columns are ALREADY in SCDB coding
# (1 = conservative, 2 = liberal, 3 = unspecifiable) and must not be remapped,
# despite what the CCAD codebook's front matter says. See references/coa.md.
scdb_songer_direction <- function(x) {
  m <- c(`0` = 3L, `1` = 1L, `2` = 3L, `3` = 2L)
  unname(m[as.character(x)])
}

# Code labels for CCAD variables, mirroring scdb_labels / scdb_label / scdb_factor.
# scdb_first_broad_area and scdb_second_sub_area reuse the SCDB issueArea / issue
# code lists exactly; the party-category, disposition and direction scales do NOT.
scdb_coa_value_labels <- function(dir = scdb_dir()) {
  utils::read.csv(file.path(dir, "references", "coa_value_labels.csv"),
                  encoding = "UTF-8", stringsAsFactors = FALSE)
}

scdb_coa_labels <- function(variable, dir = scdb_dir()) {
  v <- scdb_coa_value_labels(dir)
  v <- v[v$variable == variable, ]
  if (!nrow(v)) stop("no CCAD labels for '", variable, "'")
  stats::setNames(v$label, v$code)
}

scdb_coa_label <- function(df, vars = NULL, dir = scdb_dir()) {
  v <- scdb_coa_value_labels(dir)
  if (is.null(vars)) vars <- unique(v$variable)
  for (k in intersect(vars, intersect(unique(v$variable), names(df)))) {
    m <- scdb_coa_labels(k, dir)
    df[[paste0(k, "_label")]] <- unname(m[as.character(df[[k]])])
  }
  df
}

scdb_coa_factor <- function(x, variable, dir = scdb_dir()) {
  m <- scdb_coa_labels(variable, dir)
  factor(unname(m[as.character(x)]), levels = unname(m))
}

# Attach the deciding circuit's JCS median and SD for the year of the decision, so a
# panel can be compared with its circuit (ghp_med - circuit_median). The panel scores
# (author_ghp, ghp_*) are Giles-Hettinger-Peppers scores, the same measure behind the
# JCS appeals-judge scores, so the two share one scale. Medians run 1924-2024.
scdb_add_coa_circuit_medians <- function(d, year_col = "year", dir = scdb_dir()) {
  cm <- scdb_jcs("circuit_medians", dir)
  if (!"coa_circuit" %in% names(cm)) {
    xw <- scdb_jcs("circuits", dir)[, c("scdb_caseSource", "coa_circuit")]
    cm <- merge(cm, xw, by = "scdb_caseSource", all.x = TRUE)
  }
  cm <- cm[, c("year", "coa_circuit", "median", "sd")]
  names(cm) <- c(year_col, "circuit", "circuit_median", "circuit_sd")
  merge(d, cm, by = c(year_col, "circuit"), all.x = TRUE, sort = FALSE)
}

# ---- Courts of appeals seats (see references/coa_seats.md)
# A seat is an authorized judgeship; succession comes from the FJC's official
# Seat IDs. Occupancy ends at senior status, which vacates the judgeship.
# Circuit numbering is the JCS scheme (12 = D.C., 13 = Federal).
scdb_seats <- function(which = c("seats", "spells"), dir = scdb_dir()) {
  which <- match.arg(which)
  f <- file.path(dir, "data", "coa",
                 switch(which, seats = "coa_seats.csv.gz", spells = "coa_seat_spells.csv.gz"))
  if (!file.exists(f))
    stop(f, " is not bundled. Build it with:\n",
         "  python scripts/build_seats.py --fjc fjc-raw/federal-judicial-service.csv.gz",
         " --out data/coa\nSee references/coa_seats.md.")
  if (requireNamespace("readr", quietly = TRUE)) {
    as.data.frame(readr::read_csv(f, show_col_types = FALSE, progress = FALSE))
  } else {
    utils::read.csv(gzfile(f), encoding = "UTF-8", stringsAsFactors = FALSE)
  }
}

# Circuit x seat x year panel, derived from the spells so it cannot drift.
# A vacant seat-year is absent, so a gap in a seat's rows is a real vacancy.
scdb_seat_panel <- function(start = NULL, end = 2026, dir = scdb_dir()) {
  sp <- scdb_seats("spells", dir)
  lo <- if (is.null(start)) min(sp$occ_start) else start
  sp <- sp[sp$occ_end >= lo & sp$occ_start <= end, ]
  a <- pmax(sp$occ_start, lo); b <- pmin(sp$occ_end, end)
  i <- rep(seq_len(nrow(sp)), b - a + 1L)
  out <- sp[i, ]
  out$year <- unlist(mapply(seq, a, b, SIMPLIFY = FALSE), use.names = FALSE)
  keep <- intersect(c("circuit", "circuit_name", "seat_no", "seat_id", "year",
                      "judge_name", "state", "jcs", "pres_party", "president",
                      "occupancy", "creating_statute"), names(out))
  out <- out[, keep]
  out[order(out$circuit, out$seat_no, out$year), ]
}

# Every judge who has held one judgeship, in order.
scdb_seat_history <- function(circuit, seat_no, dir = scdb_dir()) {
  sp <- scdb_seats("spells", dir)
  sp <- sp[sp$circuit == circuit & sp$seat_no == seat_no, ]
  sp[order(sp$occupancy), ]
}

# Who sat on one circuit in one year, one row per filled seat.
scdb_court_composition <- function(circuit, year, dir = scdb_dir()) {
  p <- scdb_seat_panel(year, year, dir)
  p <- p[p$circuit == circuit, ]
  p[order(p$seat_no), ]
}
