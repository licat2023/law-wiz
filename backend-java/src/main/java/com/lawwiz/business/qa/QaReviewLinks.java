package com.lawwiz.business.qa;

import java.math.BigInteger;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** Own the cleanup of conversation links when a review is permanently deleted. */
@Service
public class QaReviewLinks {
    private final QaMapper mapper;

    QaReviewLinks(QaMapper mapper) {
        this.mapper = mapper;
    }

    /** Keep conversation history and detach the removed report and risk within the deletion transaction. */
    @Transactional(propagation = Propagation.MANDATORY)
    public void detach(BigInteger task) {
        mapper.detachReview(task);
    }
}
