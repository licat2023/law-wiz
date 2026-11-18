package com.lawwiz.business.api;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/** Render framework and business failures with the same public envelope. */
@RestControllerAdvice
public class ApiErrors {
    private static final Logger LOGGER = LoggerFactory.getLogger(ApiErrors.class);

    @ExceptionHandler(ApiError.class)
    ResponseEntity<ApiEnvelope> business(ApiError error, HttpServletRequest request) {
        return ResponseEntity.status(error.code() / 100)
                .body(new ApiEnvelope(error.code(), error.getMessage(), error.data(), RequestIds.get(request)));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiEnvelope> validation(MethodArgumentNotValidException error, HttpServletRequest request) {
        var details = error.getFieldErrors().stream()
                .map(field -> Map.of("field", field.getField().replaceAll("([A-Z])", "_$1").toLowerCase(java.util.Locale.ROOT),
                        "reason", field.getDefaultMessage() == null ? "参数不合法" : field.getDefaultMessage()))
                .toList();
        return business(new ApiError(40001, "请求参数不合法", Map.of("details", details)), request);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiEnvelope> malformed(HttpMessageNotReadableException error, HttpServletRequest request) {
        return business(new ApiError(40002, "请求体格式错误"), request);
    }

    @ExceptionHandler(NoResourceFoundException.class)
    ResponseEntity<ApiEnvelope> notFound(NoResourceFoundException error, HttpServletRequest request) {
        return business(new ApiError(40400, "请求的资源不存在"), request);
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    ResponseEntity<ApiEnvelope> method(HttpRequestMethodNotSupportedException error, HttpServletRequest request) {
        return business(new ApiError(40500, "请求方法不允许"), request);
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ApiEnvelope> fileTooLarge(MaxUploadSizeExceededException error, HttpServletRequest request) {
        return business(new ApiError(41301, "文件超出大小上限"), request);
    }

    @ExceptionHandler({MissingServletRequestParameterException.class, MissingServletRequestPartException.class,
            MethodArgumentTypeMismatchException.class})
    ResponseEntity<ApiEnvelope> parameter(Exception error, HttpServletRequest request) {
        return business(new ApiError(40001, "请求参数不合法"), request);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiEnvelope> unexpected(Exception error, HttpServletRequest request) {
        LOGGER.error("Unexpected failure for request {}", RequestIds.get(request), error);
        return business(new ApiError(50000, "服务器内部错误"), request);
    }
}
