package routes

import (
	"net/http"

	"github.com/pavelkoff/ai-auogeneration/go_server/internal/handlers"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/middleware"
)

// Register регистрирует маршруты API на mux.
func Register(mux *http.ServeMux, api *handlers.API, authMW func(http.Handler) http.Handler) {
	mux.HandleFunc("GET /health", api.Health)

	mux.Handle("POST /api/report", authMW(http.HandlerFunc(api.CreateReport)))
	mux.Handle("POST /api/kp", authMW(http.HandlerFunc(api.CreateKP)))
}

// NewMux создаёт ServeMux с зарегистрированными роутами.
func NewMux(api *handlers.API, authMW func(http.Handler) http.Handler) *http.ServeMux {
	mux := http.NewServeMux()
	Register(mux, api, authMW)
	return mux
}

// Wrap применяет глобальные middleware к mux.
func Wrap(mux http.Handler, mws ...func(http.Handler) http.Handler) http.Handler {
	return middleware.Chain(mux, mws...)
}
