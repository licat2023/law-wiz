package com.lawwiz.business.api;

import java.util.List;
import java.util.Map;

/** A business failure whose code and optional data are safe for the API response. */
public class ApiError extends RuntimeException {
    private final int code;
    private final Object data;

    public ApiError(int code, String message) {
        this(code, message, null);
    }

    public ApiError(int code, String message, Object data) {
        super(message);
        this.code = code;
        this.data = data;
    }

    public static ApiError field(int code, String field, String message) {
        return new ApiError(code, message, Map.of("details", List.of(Map.of("field", field, "reason", message))));
    }

    public int code() {
        return code;
    }

    public Object data() {
        return data;
    }
}
