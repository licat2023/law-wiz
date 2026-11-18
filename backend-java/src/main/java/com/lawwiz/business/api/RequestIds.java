package com.lawwiz.business.api;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Validate client trace identifiers and propagate one identifier per request. */
@Component
public class RequestIds extends OncePerRequestFilter {
    private static final String HEADER = "X-Request-ID";
    private static final String ATTRIBUTE = RequestIds.class.getName();
    private static final Pattern VALID = Pattern.compile("[A-Za-z0-9_-]{8,64}");

    public static String get(HttpServletRequest request) {
        return (String) request.getAttribute(ATTRIBUTE);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String incoming = request.getHeader(HEADER);
        String requestId = incoming != null && VALID.matcher(incoming).matches()
                ? incoming
                : "req_" + UUID.randomUUID().toString().replace("-", "").substring(0, 16);
        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader(HEADER, requestId);
        try (var context = MDC.putCloseable("request_id", requestId)) {
            chain.doFilter(request, response);
        }
    }
}
