package utils

import (
	"encoding/json"
	"net/http"

	"github.com/pavelkoff/ai-auogeneration/go_server/internal/models"
)

// WriteJSON пишет JSON-ответ с кодом статуса.
func WriteJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// WriteError пишет {"error": "..."}.
func WriteError(w http.ResponseWriter, status int, msg string) {
	WriteJSON(w, status, models.ErrorResponse{Error: msg})
}

// WritePDFFile отдаёт PDF как attachment.
func WritePDFFile(w http.ResponseWriter, r *http.Request, absPath, downloadName string) {
	w.Header().Set("Content-Type", "application/pdf")
	w.Header().Set("Content-Disposition", `attachment; filename="`+downloadName+`"`)
	http.ServeFile(w, r, absPath)
}
