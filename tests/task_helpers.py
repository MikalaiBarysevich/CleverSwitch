"""Shared helpers for InfoTask unit tests."""

from __future__ import annotations


def deliver_on_request(task, topics, responses) -> None:
    """Hand *responses* to *task* one per request, as the real transport would.

    InfoTask._send_request drains the response queue before publishing, because anything already
    queued predates the request it is about to send. A response parked in the queue *before*
    doTask() runs is therefore discarded — correctly, since that ordering cannot happen on real
    hardware. Deliver each response when its request is published instead.

    Fewer responses than requests leaves the remaining waits to time out, which is what a silent
    device looks like.
    """
    pending = list(responses)

    def _on_publish(*_args, **_kwargs):
        if pending:
            task._response_queue.put(pending.pop(0))

    topics.write.publish.side_effect = _on_publish
