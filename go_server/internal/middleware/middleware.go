package middleware

import (
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/pavelkoff/ai-auogeneration/go_server/internal/utils"
)

// APITokenAuth проверяет X-API-Token / Bearer; без токена — только loopback.
func APITokenAuth(token string, log *slog.Logger) func(http.Handler) http.Handler {
	if log == nil {
		log = slog.Default()
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if token == "" {
				host := utils.ClientHost(r.RemoteAddr)
				if !utils.IsLoopback(host) && !utils.IsLoopback(r.RemoteAddr) {
					log.Warn("rejected unauthenticated remote request", "remote", r.RemoteAddr)
					utils.WriteError(w, http.StatusUnauthorized, utils.ErrAuthRequired.Error())
					return
				}
				next.ServeHTTP(w, r)
				return
			}

			header := strings.TrimSpace(r.Header.Get("X-API-Token"))
			auth := strings.TrimSpace(r.Header.Get("Authorization"))
			bearer := ""
			if len(auth) >= 7 && strings.EqualFold(auth[:7], "bearer ") {
				bearer = strings.TrimSpace(auth[7:])
			}
			provided := header
			if provided == "" {
				provided = bearer
			}
			if provided != token {
				utils.WriteError(w, http.StatusUnauthorized, utils.ErrUnauthorized.Error())
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// BodyLimit ограничивает размер тела запроса.
func BodyLimit(maxBytes int64) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Body != nil {
				r.Body = http.MaxBytesReader(w, r.Body, maxBytes)
			}
			next.ServeHTTP(w, r)
		})
	}
}

// RequestLogger логирует method/path/status/duration.
func RequestLogger(log *slog.Logger) func(http.Handler) http.Handler {
	if log == nil {
		log = slog.Default()
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			rw := &statusWriter{ResponseWriter: w, status: http.StatusOK}
			next.ServeHTTP(rw, r)
			log.Info("request",
				"method", r.Method,
				"path", r.URL.Path,
				"status", rw.status,
				"remote", r.RemoteAddr,
				"dur_ms", time.Since(start).Milliseconds(),
			)
		})
	}
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}

// Chain применяет middleware справа налево: Chain(h, A, B) => A(B(h)).
func Chain(h http.Handler, mws ...func(http.Handler) http.Handler) http.Handler {
	for i := len(mws) - 1; i >= 0; i-- {
		h = mws[i](h)
	}
	return h
}
