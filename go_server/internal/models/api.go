package models

// HealthResponse — ответ GET /health.
type HealthResponse struct {
	Status string `json:"status"`
}

// ErrorResponse — единый формат ошибок API.
type ErrorResponse struct {
	Error string `json:"error"`
}

// ReportJSONRequest — JSON-тело POST /api/report.
type ReportJSONRequest struct {
	Text string `json:"text"`
	Type string `json:"type"`
}

// DialogInput — нормализованные данные транскрибации из JSON / form / file.
type DialogInput struct {
	Text       string
	TypeRaw    string
	ReportType string
}

// KPRequest — JSON-тело POST /api/kp.
type KPRequest struct {
	WithFZ          bool   `json:"with_fz"`
	WithEngineering bool   `json:"with_engineering"`
	Text            string `json:"text"`
	ClientName      string `json:"client_name"`
}

// KPResponse — ответ POST /api/kp.
type KPResponse struct {
	WithFZ          bool     `json:"with_fz"`
	WithEngineering bool     `json:"with_engineering"`
	Files           []string `json:"files"`
}

// ReportResult — результат генерации PDF-отчёта.
type ReportResult struct {
	AbsPath      string
	DownloadName string
}
