package handlers

import (
	"log/slog"
	"net/http"

	"github.com/pavelkoff/ai-auogeneration/go_server/internal/models"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/services"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/utils"
)

// API объединяет HTTP-обработчики.
type API struct {
	log       *slog.Logger
	generator *services.GeneratorService
}

// New создаёт набор handlers.
func New(log *slog.Logger, generator *services.GeneratorService) *API {
	if log == nil {
		log = slog.Default()
	}
	return &API{log: log, generator: generator}
}

// Health — GET /health.
func (a *API) Health(w http.ResponseWriter, r *http.Request) {
	utils.WriteJSON(w, http.StatusOK, models.HealthResponse{Status: "ok"})
}

// CreateReport — POST /api/report.
func (a *API) CreateReport(w http.ResponseWriter, r *http.Request) {
	input, err := utils.ParseDialogInput(r)
	if err != nil {
		status := http.StatusBadRequest
		utils.WriteError(w, status, err.Error())
		return
	}

	result, err := a.generator.CreateReport(r.Context(), input.Text, input.ReportType)
	if err != nil {
		a.log.Error("report failed", "err", err)
		utils.WriteError(w, http.StatusInternalServerError, "Внутренняя ошибка сервера")
		return
	}

	utils.WritePDFFile(w, r, result.AbsPath, result.DownloadName)
}

// CreateKP — POST /api/kp.
func (a *API) CreateKP(w http.ResponseWriter, r *http.Request) {
	var req models.KPRequest
	if err := utils.DecodeJSONBody(r, &req); err != nil {
		utils.WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	resp, err := a.generator.GenerateKP(r.Context(), req)
	if err != nil {
		a.log.Error("kp failed", "err", err)
		utils.WriteError(w, http.StatusInternalServerError, "Внутренняя ошибка сервера")
		return
	}

	utils.WriteJSON(w, http.StatusOK, resp)
}
