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

scdb_dir <- function() {
  cands <- c(Sys.getenv("SCDB_SKILL_DIR"),
             file.path(path.expand("~"), ".claude", "skills", "scdb-expert"),
             "/mnt/skills/user/scdb-expert")
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
