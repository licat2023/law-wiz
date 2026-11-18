package com.lawwiz.business.qa;

import java.math.BigInteger;

import com.lawwiz.business.api.ApiEnvelope;
import com.lawwiz.business.api.ApiValues;
import com.lawwiz.business.api.Idempotency;
import com.lawwiz.business.api.RateLimits;
import com.lawwiz.business.api.RequestIds;
import com.lawwiz.business.auth.AccessTokens;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** Serve ordinary and report-associated conversations under the existing QA API. */
@RestController
@RequestMapping("/api/qa/sessions")
class QaController {
    record NewSession(@Size(max = 200) String title, String reviewTaskId, String riskPointId) {}
    record Question(@NotNull @Size(min = 1, max = 4000) String content) {}

    private final QaService qa;
    private final AccessTokens tokens;
    private final Idempotency idempotency;
    private final RateLimits limits;
    private final int readLimit;
    private final int pollLimit;
    private final int aiLimit;

    QaController(QaService qa, AccessTokens tokens, Idempotency idempotency, RateLimits limits,
                 @Value("${LAWWIZ_RATE_LIMIT_READ_PER_MINUTE:120}") int readLimit,
                 @Value("${LAWWIZ_RATE_LIMIT_POLL_PER_MINUTE:60}") int pollLimit,
                 @Value("${LAWWIZ_RATE_LIMIT_AI_PER_MINUTE:10}") int aiLimit) {
        this.qa = qa;
        this.tokens = tokens;
        this.idempotency = idempotency;
        this.limits = limits;
        this.readLimit = readLimit;
        this.pollLimit = pollLimit;
        this.aiLimit = aiLimit;
    }

    @PostMapping
    @ResponseStatus(org.springframework.http.HttpStatus.CREATED)
    ApiEnvelope create(@Valid @RequestBody NewSession payload, HttpServletRequest request, HttpServletResponse response) {
        var owner = authorize(request, response, "read", readLimit);
        return ApiEnvelope.success(qa.create(owner, payload.title(), optionalId(payload.reviewTaskId()),
                optionalId(payload.riskPointId())), request);
    }

    @GetMapping
    ApiEnvelope list(@RequestParam(defaultValue = "1") int page,
                     @RequestParam(name = "page_size", defaultValue = "20") int pageSize,
                     @RequestParam(name = "status", required = false) String status,
                     @RequestParam(defaultValue = "-last_message_at") String sort,
                     HttpServletRequest request, HttpServletResponse response) {
        var owner = authorize(request, response, "read", readLimit);
        return ApiEnvelope.success(qa.list(owner, status, sort, page, pageSize), request);
    }

    @GetMapping("/{id}")
    ApiEnvelope detail(@PathVariable String id,
                       @RequestParam(defaultValue = "1") int page,
                       @RequestParam(name = "page_size", defaultValue = "20") int pageSize,
                       HttpServletRequest request, HttpServletResponse response) {
        var owner = authorize(request, response, "poll", pollLimit);
        return ApiEnvelope.success(qa.detail(owner, ApiValues.id(id), page, pageSize), request);
    }

    @PostMapping("/{id}/messages")
    @ResponseStatus(org.springframework.http.HttpStatus.ACCEPTED)
    ApiEnvelope ask(@PathVariable String id, @Valid @RequestBody Question payload,
                    HttpServletRequest request, HttpServletResponse response) {
        var owner = authorize(request, response, "ai", aiLimit);
        var session = ApiValues.id(id);
        var result = idempotency.submit("qa:" + owner + ":" + session, request.getHeader("Idempotency-Key"),
                () -> qa.ask(owner, session, payload.content(), RequestIds.get(request)));
        return ApiEnvelope.success(result, request);
    }

    @GetMapping("/{id}/messages/{messageId}/stream")
    ResponseEntity<SseEmitter> stream(@PathVariable String id, @PathVariable String messageId,
                                      HttpServletRequest request, HttpServletResponse response) {
        var owner = authorize(request, response, "poll", pollLimit);
        var stream = qa.stream(owner, ApiValues.id(id), ApiValues.id(messageId));
        return ResponseEntity.ok().contentType(MediaType.TEXT_EVENT_STREAM)
                .header("Cache-Control", "no-store").header("X-Accel-Buffering", "no").body(stream);
    }

    @DeleteMapping("/{id}")
    ApiEnvelope archive(@PathVariable String id, HttpServletRequest request, HttpServletResponse response) {
        var owner = authorize(request, response, "read", readLimit);
        qa.archive(owner, ApiValues.id(id));
        return ApiEnvelope.success(null, request);
    }

    private BigInteger authorize(HttpServletRequest request, HttpServletResponse response, String category, int limit) {
        BigInteger user = tokens.requireUser(request.getHeader("Authorization"));
        limits.require(category, user.toString(), limit, response);
        return user;
    }

    private BigInteger optionalId(String id) {
        return id == null ? null : ApiValues.id(id);
    }
}
