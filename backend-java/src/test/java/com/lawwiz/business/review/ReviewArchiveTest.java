package com.lawwiz.business.review;

import java.math.BigInteger;
import java.time.LocalDateTime;

import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.files.BusinessFiles;
import com.lawwiz.business.qa.QaReviewLinks;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** Pin ownership and the irreversible transition out of the archive. */
class ReviewArchiveTest {
    private static final BigInteger OWNER = BigInteger.ONE;
    private static final BigInteger TASK = BigInteger.TWO;
    private final ReviewMapper mapper = mock(ReviewMapper.class);
    private final QaReviewLinks links = mock(QaReviewLinks.class);
    private final ReviewService reviews = service();

    @Test
    void togglesTheArchiveOnlyForItsOwner() {
        task("processing", null);
        assertEquals(40301, assertThrows(ApiError.class,
                () -> reviews.setArchived(BigInteger.TEN, TASK, true)).code());
        reviews.setArchived(OWNER, TASK, true);
        verify(mapper).setArchived(TASK, true);
        reviews.setArchived(OWNER, TASK, false);
        verify(mapper).setArchived(TASK, false);
    }

    @Test
    void onlyAnArchivedFinishedTaskCanBePermanentlyDeleted() {
        when(mapper.lockOwner(OWNER)).thenReturn(OWNER);
        task("succeeded", null);
        assertEquals(40910, assertThrows(ApiError.class, () -> reviews.deleteArchived(OWNER, TASK)).code());
        task("processing", LocalDateTime.of(2026, 11, 19, 9, 0));
        assertEquals(40910, assertThrows(ApiError.class, () -> reviews.deleteArchived(OWNER, TASK)).code());
        verify(mapper, never()).deleteTask(TASK);

        task("succeeded", LocalDateTime.of(2026, 11, 19, 9, 0));
        reviews.deleteArchived(OWNER, TASK);
        verify(links).detach(TASK);
        verify(mapper).deleteReport(TASK);
        verify(mapper).deletePoints(TASK);
        verify(mapper).deleteTask(TASK);
    }

    private ReviewService service() {
        var manager = mock(PlatformTransactionManager.class);
        when(manager.getTransaction(any())).thenAnswer(ignored -> new SimpleTransactionStatus());
        return new ReviewService(mapper, mock(BusinessFiles.class), null, null,
                new TransactionTemplate(manager), null, null, links);
    }

    private void task(String state, LocalDateTime archivedAt) {
        when(mapper.lockTask(TASK)).thenReturn(new ReviewMapper.Task(
                TASK, OWNER, null, null, state, null, 0, null, null, null, null, null, null, archivedAt));
    }
}
