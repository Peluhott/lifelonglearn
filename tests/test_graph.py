from tutor.graph import graph
from tutor.schemas import IntakeResult, PlannerResult, ReviewerResult, TeacherResult


def run(prompt="help me with the chain rule"):
    return graph.invoke({"user_prompt": prompt}, config={"recursion_limit": 50})


def test_full_run_teaches_every_step_then_reviews(fake_llm):
    final = run()

    assert fake_llm.calls == [IntakeResult, PlannerResult, TeacherResult, TeacherResult, ReviewerResult]
    assert [t.step for t in final["teacher"]] == ["step one", "step two"]
    assert final["planner_index"] == 2
    assert [q.step for q in final["reviewer"].questions] == ["step one", "step two"]


def test_plan_with_no_steps_skips_teacher_and_review(fake_llm):
    fake_llm.steps = []

    final = run()

    assert fake_llm.calls == [IntakeResult, PlannerResult]
    assert final.get("teacher", []) == []
    assert "reviewer" not in final


def test_image_only_made_when_teacher_asks_for_one(fake_image):
    final = run()

    first, second = final["teacher"]
    assert first.image == "fake.png"
    assert second.image is None
    assert fake_image.prompts == ["diagram of step one"]


def test_failed_image_does_not_stop_the_lesson(fake_image, capsys):
    fake_image.error = RuntimeError("image model down")

    final = run()

    assert len(final["teacher"]) == 2
    assert final["teacher"][0].image is None
    assert "Image generation failed for step 1" in capsys.readouterr().out
