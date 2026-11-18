package com.lawwiz.business.qa;

import java.math.BigInteger;
import java.util.List;
import java.util.Map;

import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.api.BackgroundTasks;
import com.lawwiz.business.review.ReportContexts;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** Exercise archive state transitions and the guard around running answer streams. */
class QaArchiveTest {
    private static final BigInteger OWNER = BigInteger.ONE;
    private static final BigInteger SESSION = BigInteger.TWO;
    private static final BigInteger ANSWER = BigInteger.valueOf(4);
    private final QaMapper mapper = mock(QaMapper.class);
    private final QaService qa = new QaService(mapper, mock(ReportContexts.class), null,
            new TransactionTemplate(new TestTransactions()), mock(BackgroundTasks.class), null);

    @Test
    void archiveAndRestoreRequireOwnershipAndKeepMessages() {
        session("active");
        assertEquals(40301, assertThrows(ApiError.class, () -> qa.setArchived(BigInteger.TEN, SESSION, true)).code());
        qa.setArchived(OWNER, SESSION, true);
        verify(mapper).setStatus(SESSION, "archived");
        session("archived");
        qa.setArchived(OWNER, SESSION, false);
        verify(mapper).setStatus(SESSION, "active");
        verify(mapper, never()).deleteMessages(SESSION);
    }

    @Test
    void deletesOnlyAnOwnedArchiveInReferenceOrder() {
        session("active");
        assertEquals(40911, assertThrows(ApiError.class, () -> qa.deleteArchived(OWNER, SESSION)).code());
        session("archived");
        assertEquals(40301, assertThrows(ApiError.class, () -> qa.deleteArchived(BigInteger.TEN, SESSION)).code());
        qa.deleteArchived(OWNER, SESSION);
        var order = inOrder(mapper);
        order.verify(mapper).deleteCitations(SESSION);
        order.verify(mapper).deleteMessages(SESSION);
        order.verify(mapper).deleteSession(SESSION);
    }

    @Test
    void runningAnswerBlocksDeletionButAnAbandonedPlaceholderDoesNot() {
        session("active");
        doAnswer(invocation -> {
            Map<String, Object> message = invocation.getArgument(0);
            message.put("id", "assistant".equals(message.get("role")) ? ANSWER : BigInteger.valueOf(3));
            return null;
        }).when(mapper).createMessage(anyMap());
        qa.ask(OWNER, SESSION, "测试问题", "fixture-request");
        session("archived");
        when(mapper.pendingAnswers(SESSION)).thenReturn(List.of(ANSWER));
        assertEquals(40911, assertThrows(ApiError.class, () -> qa.deleteArchived(OWNER, SESSION)).code());
        verify(mapper, never()).deleteSession(SESSION);

        when(mapper.pendingAnswers(SESSION)).thenReturn(List.of(BigInteger.TEN));
        qa.deleteArchived(OWNER, SESSION);
        verify(mapper).deleteSession(SESSION);
    }

    private void session(String status) {
        when(mapper.lock(SESSION)).thenReturn(new QaMapper.Session(
                SESSION, OWNER, null, null, "测试会话", status, 0, null, null));
    }

    private static final class TestTransactions extends AbstractPlatformTransactionManager {
        @Override protected Object doGetTransaction() { return new Object(); }
        @Override protected void doBegin(Object transaction, TransactionDefinition definition) {}
        @Override protected void doCommit(DefaultTransactionStatus status) {}
        @Override protected void doRollback(DefaultTransactionStatus status) {}
    }
}
