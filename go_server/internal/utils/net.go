package utils

import (
	"net"
	"strings"
)

// ClientHost извлекает IP/host из RemoteAddr.
func ClientHost(remoteAddr string) string {
	host, _, err := net.SplitHostPort(remoteAddr)
	if err != nil || host == "" {
		return remoteAddr
	}
	return host
}

// IsLoopback проверяет loopback-адрес (с портом или без).
func IsLoopback(addr string) bool {
	host := addr
	if strings.HasPrefix(addr, "[") {
		if end := strings.Index(addr, "]"); end > 0 {
			host = addr[1:end]
		}
	} else if i := strings.LastIndex(addr, ":"); i >= 0 {
		// IPv4 host:port — не трогаем голый IPv6 без скобок
		if strings.Count(addr, ":") == 1 {
			host = addr[:i]
		}
	}
	host = strings.TrimSpace(host)
	switch host {
	case "127.0.0.1", "::1", "localhost", "":
		return true
	default:
		return false
	}
}
