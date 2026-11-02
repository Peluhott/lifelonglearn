import threading

from tutor.graph import graph
from tutor.schemas import IntakeResult, PlannerResult, ReviewerResult, TeacherResult


def run(prompt="help me with the chain rule"):
    return graph.invoke({"user_prompt": prompt})


def taught_in_order(final):
    return sorted(final["teacher"], key=lambda t: t.index)


def test_full_run_teaches_every_step_then_reviews(fake_llm):
    final = run()

    assert fake_llm.calls == [IntakeResult, PlannerResult, TeacherResult, TeacherResult, ReviewerResult]
    assert [(t.index, t.step) for t in taught_in_order(final)] == [(0, "step one"), (1, "step two")]
    assert [q.step for q in final["reviewer"].questions] == ["step one", "step two"]


def test_teachers_run_in_parallel(fake_llm):
    fake_llm.steps = ["a", "b", "c"]
    # each teacher blocks until all 3 are waiting; if they ran one at a time the barrier would time out
    fake_llm.teacher_barrier = threading.Barrier(3, timeout=2)

    final = run()

    assert [t.step for t in taught_in_order(final)] == ["a", "b", "c"]


def test_plan_with_no_steps_skips_teacher_and_review(fake_llm):
    fake_llm.steps = []

    final = run()

    assert fake_llm.calls == [IntakeResult, PlannerResult]
    assert final.get("teacher", []) == []
    assert "reviewer" not in final


def test_image_only_made_when_teacher_asks_for_one(fake_image):
    final = run()

    first, second = taught_in_order(final)
    assert first.image == "fake.png"
    assert second.image is None
    assert fake_image.prompts == ["diagram of step one"]


def test_failed_image_does_not_stop_the_lesson(fake_image, capsys):
    fake_image.error = RuntimeError("image model down")

    final = run()

    assert len(final["teacher"]) == 2
    assert taught_in_order(final)[0].image is None
    assert "Image generation failed for step 1" in capsys.readouterr().out
