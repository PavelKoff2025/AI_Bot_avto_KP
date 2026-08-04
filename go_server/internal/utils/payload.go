package utils

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"

	"github.com/pavelkoff/ai-auogeneration/go_server/internal/models"
)

var reportTypeAliases = map[string]string{
	"1": "client", "client": "client",
	"2": "design", "design": "design",
	"3": "ar", "ar": "ar",
	"4": "engineering", "engineering": "engineering", "ir": "engineering",
}

// ResolveReportType нормализует алиас типа отчёта.
func ResolveReportType(raw string) (string, error) {
	key := strings.ToLower(strings.TrimSpace(raw))
	if key == "" {
		return "", ErrReportType
	}
	v, ok := reportTypeAliases[key]
	if !ok {
		return "", ErrReportType
	}
	return v, nil
}

// ParseDialogInput читает text/type из JSON, multipart или form.
func ParseDialogInput(r *http.Request) (models.DialogInput, error) {
	out := models.DialogInput{TypeRaw: "client"}
	ct := r.Header.Get("Content-Type")

	if strings.HasPrefix(ct, "application/json") {
		var payload models.ReportJSONRequest
		dec := json.NewDecoder(io.LimitReader(r.Body, MaxUploadBytes+1))
		if err := dec.Decode(&payload); err != nil {
			return out, ErrBadJSON
		}
		out.Text = strings.TrimSpace(payload.Text)
		if strings.TrimSpace(payload.Type) != "" {
			out.TypeRaw = payload.Type
		}
		return finalizeDialog(out)
	}

	if strings.HasPrefix(ct, "multipart/form-data") {
		if err := r.ParseMultipartForm(MaxUploadBytes); err != nil {
			return out, ErrUpload
		}
		if v := r.FormValue("type"); v != "" {
			out.TypeRaw = v
		}
		if v := strings.TrimSpace(r.FormValue("text")); v != "" {
			out.Text = v
			return finalizeDialog(out)
		}
		file, _, err := r.FormFile("file")
		if err != nil {
			return out, ErrNeedText
		}
		defer file.Close()
		raw, err := io.ReadAll(io.LimitReader(file, MaxUploadBytes+1))
		if err != nil {
			return out, err
		}
		if len(raw) > MaxUploadBytes {
			return out, ErrTooLarge
		}
		out.Text = strings.TrimSpace(string(raw))
		return finalizeDialog(out)
	}

	if err := r.ParseForm(); err == nil {
		if v := r.FormValue("type"); v != "" {
			out.TypeRaw = v
		}
		if v := strings.TrimSpace(r.FormValue("text")); v != "" {
			out.Text = v
			return finalizeDialog(out)
		}
	}
	return out, ErrNeedText
}

// DecodeJSONBody декодирует JSON в dest с лимитом размера.
func DecodeJSONBody(r *http.Request, dest any) error {
	if r.Body == nil {
		return nil
	}
	dec := json.NewDecoder(io.LimitReader(r.Body, MaxUploadBytes+1))
	if err := dec.Decode(dest); err != nil && err != io.EOF {
		return ErrBadJSON
	}
	return nil
}

func finalizeDialog(in models.DialogInput) (models.DialogInput, error) {
	if in.Text == "" {
		return in, ErrNeedText
	}
	rt, err := ResolveReportType(in.TypeRaw)
	if err != nil {
		return in, err
	}
	in.ReportType = rt
	return in, nil
}
