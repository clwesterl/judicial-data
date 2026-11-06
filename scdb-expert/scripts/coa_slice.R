# coa_slice.R -- extract a small, sendable slice of the Comprehensive Court of Appeals Database.
#
# Run from this folder, in Terminal:
#     cd ~/Desktop/coa\ data
#     Rscript coa_slice.R
#
# The RData is uncompressed, so load() needs roughly 6-8 GB of RAM and a few
# minutes. It writes three gzipped CSVs beside the data:
#     coa_columns.csv.gz        all 809 columns: type, missing count, example value
#     coa_link.csv.gz           every case, linkage/identifier columns only
#     coa_scotus_bridge.csv.gz  just the cases the Supreme Court reviewed

t0 <- Sys.time()
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

## ---- 1. full column inventory (the important one; always written) ----------
probe <- df[seq_len(min(3000L, nrow(df))), , drop = FALSE]
width <- vapply(probe, function(x) if (is.character(x)) max(c(0L, nchar(x)), na.rm = TRUE) else 0L, integer(1))
first_val <- function(x) {
  v <- x[!is.na(x)]
  if (!length(v)) "" else substr(gsub("[\r\n\t]+", " ", as.character(v[1])), 1, 100)
}
info <- data.frame(column    = names(df),
                   type      = vapply(df, function(x) class(x)[1], character(1)),
                   max_chars = width[names(df)],
                   n_missing = vapply(df, function(x) sum(is.na(x)), numeric(1)),
                   example   = vapply(probe, first_val, character(1)),
                   row.names = NULL, stringsAsFactors = FALSE)
write.csv(info, gzfile("coa_columns.csv.gz"), row.names = FALSE)
say("wrote coa_columns.csv.gz  (", nrow(info), " columns documented)")

## ---- 2. pick the linkage columns by pattern, not by guessed names ----------
keep <- grepl(paste0("(^|_)(caseid|case_id|id|cite|citation|circuit|court|year|date|",
                     "docket|docket_number|volume|reporter|page|",
                     "appellant|respondent|petitioner|appellee|part(y|ies)|",
                     "disposition|issue|direction|outcome|",
                     "supct|scotus|supreme|cert|",
                     "songer|idb|crosswalk|match|source|enbanc|judge_count|",
                     "n_opinions|n_dissent|n_concur)($|_)"),
              names(df), ignore.case = TRUE)
drop <- grepl("justification|reason|rationale|explanation|summary|quote|excerpt|text|json|blob|note",
              names(df), ignore.case = TRUE) | (width[names(df)] > 200)
cols <- names(df)[keep & !drop]
say("selected ", length(cols), " linkage columns")
writeLines(cols, "coa_link_columns.txt")

link <- df[, cols, drop = FALSE]
write.csv(link, gzfile("coa_link.csv.gz"), row.names = FALSE)
say("wrote coa_link.csv.gz  (", nrow(link), " rows x ", ncol(link), " columns)")

## ---- 3. the SCOTUS-review subset ------------------------------------------
flag <- grep("supct|scotus|supreme", names(df), ignore.case = TRUE, value = TRUE)
say("Supreme-Court-related columns: ", if (length(flag)) paste(flag, collapse = ", ") else "(none found)")
hit <- rep(FALSE, nrow(df))
for (f in flag) {
  v <- df[[f]]
  if (is.numeric(v)) hit <- hit | (!is.na(v) & v == 1)
}
if (any(hit)) {
  write.csv(df[hit, union(cols, flag), drop = FALSE],
            gzfile("coa_scotus_bridge.csv.gz"), row.names = FALSE)
  say("wrote coa_scotus_bridge.csv.gz  (", sum(hit), " rows)")
} else say("no rows flagged as Supreme-Court-reviewed; see coa_columns.csv.gz")

for (f in c("coa_columns.csv.gz", "coa_link.csv.gz", "coa_scotus_bridge.csv.gz"))
  if (file.exists(f)) say(sprintf("  %-28s %7.1f MB", f, file.size(f) / 1e6))
say(sprintf("done in %.1f min", as.numeric(difftime(Sys.time(), t0, units = "mins"))))
