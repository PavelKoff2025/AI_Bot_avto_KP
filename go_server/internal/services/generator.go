package services

import (
	"context"
	"fmt"
	"strings"

	"github.com/pavelkoff/ai-auogeneration/go_server/internal/bridge"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/models"
)

// GeneratorService — бизнес-логика генерации отчётов и КП.
type GeneratorService struct {
	bridge *bridge.Client
}

// NewGenerator создаёт сервис поверх Python bridge.
func NewGenerator(b *bridge.Client) *GeneratorService {
	return &GeneratorService{bridge: b}
}

// CreateReport генерирует PDF-отчёт.
func (s *GeneratorService) CreateReport(ctx context.Context, text, reportType string) (models.ReportResult, error) {
	raw, err := s.bridge.Call(ctx, models.BridgeReportRequest{
		Action: models.BridgeActionReport,
		Text:   text,
		Type:   reportType,
	})
	if err != nil {
		return models.ReportResult{}, err
	}
	if !raw.OK {
		return models.ReportResult{}, fmt.Errorf("%s", raw.Error)
	}

	abs, err := s.bridge.ResolvePath(raw.Path)
	if err != nil {
		return models.ReportResult{}, err
	}
	name := raw.Name
	if name == "" {
		name = bridge.BaseName(abs)
	}
	return models.ReportResult{AbsPath: abs, DownloadName: name}, nil
}

// GenerateKP формирует комплект КП.
func (s *GeneratorService) GenerateKP(ctx context.Context, req models.KPRequest) (models.KPResponse, error) {
	clientName := strings.TrimSpace(req.ClientName)
	raw, err := s.bridge.Call(ctx, models.BridgeKPRequest{
		Action:          models.BridgeActionKP,
		Text:            strings.TrimSpace(req.Text),
		WithFZ:          req.WithFZ,
		WithEngineering: req.WithEngineering,
		ClientName:      clientName,
	})
	if err != nil {
		return models.KPResponse{}, err
	}
	if !raw.OK {
		return models.KPResponse{}, fmt.Errorf("%s", raw.Error)
	}
	return models.KPResponse{
		WithFZ:          req.WithFZ,
		WithEngineering: req.WithEngineering,
		Files:           raw.Files,
	}, nil
}
