#!/usr/bin/env Rscript

# Fixed JSON runner for the optional Agent Hub R Direct adapter.
suppressPackageStartupMessages(library(jsonlite))

`%||%` <- function(x, y) if (is.null(x)) y else x

fail <- function(message, status = 2L) {
  cat(toJSON(list(success = FALSE, error = message), auto_unbox = TRUE, null = "null"))
  quit(status = status)
}

request_text <- paste(readLines(file("stdin"), warn = FALSE), collapse = "\n")
request <- tryCatch(fromJSON(request_text, simplifyVector = FALSE), error = function(e) fail("Invalid JSON request"))
if (!identical(request$contract_version, "1.0")) fail("Unsupported contract version")
operation <- as.character(request$operation %||% "")
params <- request$params %||% list()

read_bounded_table <- function(path, delimiter = "auto") {
  if (!nzchar(path) || !file.exists(path)) fail("Input table does not exist")
  if (identical(delimiter, "auto")) delimiter <- if (grepl("\\.tsv$|\\.txt$", path, ignore.case = TRUE)) "\t" else ","
  if (!delimiter %in% c(",", "\t", ";")) fail("Unsupported delimiter")
  tryCatch(
    read.table(path, header = TRUE, sep = delimiter, nrows = 10000L, check.names = FALSE,
               comment.char = "", quote = "\"", stringsAsFactors = FALSE),
    error = function(e) fail("Unable to read input table")
  )
}

if (identical(operation, "preflight")) {
  result <- list(
    success = TRUE,
    operation = operation,
    data = list(jsonlite = as.character(packageVersion("jsonlite"))),
    versions = list(R = as.character(getRversion()), jsonlite = as.character(packageVersion("jsonlite"))),
    artifacts = list()
  )
} else if (identical(operation, "summarize_table")) {
  path <- as.character(params$path %||% "")
  delimiter <- as.character(params$delimiter %||% "auto")
  table <- read_bounded_table(path, delimiter)
  result <- list(
    success = TRUE,
    operation = operation,
    data = list(rows_read = nrow(table), columns = ncol(table), column_names = names(table)),
    versions = list(R = as.character(getRversion()), jsonlite = as.character(packageVersion("jsonlite"))),
    artifacts = list()
  )
} else if (identical(operation, "preview_dataset")) {
  data <- read_bounded_table(as.character(params$data_path %||% ""), as.character(params$delimiter %||% "auto"))
  metadata <- read_bounded_table(as.character(params$metadata_path %||% ""), as.character(params$delimiter %||% "auto"))
  sample_column <- as.character(params$sample_id_column %||% names(metadata)[1])
  if (!sample_column %in% names(metadata)) fail("Metadata sample ID column does not exist")
  metadata_ids <- unique(trimws(as.character(metadata[[sample_column]])))
  metadata_ids <- metadata_ids[nzchar(metadata_ids)]
  column_ids <- names(data)[-1]
  row_ids <- if (ncol(data) > 0L) trimws(as.character(data[[1]])) else character()
  column_overlap <- length(intersect(column_ids, metadata_ids))
  row_overlap <- length(intersect(row_ids, metadata_ids))
  orientation <- if (column_overlap >= row_overlap) "features_in_rows" else "samples_in_rows"
  matched <- max(column_overlap, row_overlap)
  result <- list(
    success = TRUE,
    operation = operation,
    data = list(
      data = list(rows = nrow(data), columns = ncol(data), orientation = orientation),
      metadata = list(rows = nrow(metadata), sample_id_column = sample_column),
      sample_overlap = list(
        assay = if (identical(orientation, "features_in_rows")) length(column_ids) else length(row_ids),
        metadata = length(metadata_ids),
        matched = matched
      ),
      warnings = if (matched == 0L) list("No matching sample identifiers") else list()
    ),
    versions = list(R = as.character(getRversion()), jsonlite = as.character(packageVersion("jsonlite"))),
    artifacts = list()
  )
} else {
  fail("Operation is not allowlisted")
}

cat(toJSON(result, auto_unbox = TRUE, null = "null", dataframe = "rows"))
