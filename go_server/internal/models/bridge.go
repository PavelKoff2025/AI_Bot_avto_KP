package models

// BridgeAction — действие для Python bridge.
const (
	BridgeActionReport = "report"
	BridgeActionKP     = "kp"
)

// BridgeReportRequest — JSON в stdin bridge для отчёта.
type BridgeReportRequest struct {
	Action string `json:"action"`
	Text   string `json:"text"`
	Type   string `json:"type"`
}

// BridgeKPRequest — JSON в stdin bridge для КП.
type BridgeKPRequest struct {
	Action          string `json:"action"`
	Text            string `json:"text,omitempty"`
	WithFZ          bool   `json:"with_fz"`
	WithEngineering bool   `json:"with_engineering"`
	ClientName      string `json:"client_name,omitempty"`
}

// BridgeResponse — JSON из stdout bridge.
type BridgeResponse struct {
	OK              bool     `json:"ok"`
	Error           string   `json:"error,omitempty"`
	Path            string   `json:"path,omitempty"`
	Name            string   `json:"name,omitempty"`
	Files           []string `json:"files,omitempty"`
	WithFZ          bool     `json:"with_fz,omitempty"`
	WithEngineering bool     `json:"with_engineering,omitempty"`
}
