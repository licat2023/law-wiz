package com.lawwiz.business.api;

import jakarta.servlet.http.HttpServletRequest;

/** Public response shape shared with the previous backend. */
public record ApiEnvelope(int code, String message, Object data, String requestId) {
    public static ApiEnvelope success(Object data, HttpServletRequest request) {
        return new ApiEnvelope(0, "ok", data, RequestIds.get(request));
    }
}
