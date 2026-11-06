import threading
import uuid

from langgraph.types import Command

from tutor.graph import graph
from tutor.schemas import IntakeResult, PlannerResult, ReteachResult, ReviewerResult, TeacherResult


def run(prompt="help me with the chain rule"):
    """Run until the graph finishes or pauses for quiz answers; returns ((state values, pending quiz or None), config)."""
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    graph.invoke({"user_prompt": prompt}, config=config)
    return state(config), config


def state(config):
    snapshot = graph.get_state(config)
    quiz = snapshot.interrupts[0].value if snapshot.interrupts else None
    return snapshot.values, quiz


def answer(config, picks):
    graph.invoke(Command(resume=picks), config=config)
    return state(config)


def taught_in_order(values):
    return sorted(values["teacher"], key=lambda t: t.index)


def test_full_run_teaches_every_step_then_reviews(fake_llm):
    (values, _), _ = run()

    assert fake_llm.calls == [IntakeResult, PlannerResult, TeacherResult, TeacherResult, ReviewerResult]
    assert [(t.index, t.step) for t in taught_in_order(values)] == [(0, "step one"), (1, "step two")]
    assert [q.step for q in values["reviewer"].questions] == ["step one", "step two"]


def test_graph_pauses_for_answers_without_revealing_them():
    (values, quiz), _ = run()

    assert values.get("grader", []) == []
    assert quiz["round"] == 1
    assert [(q["index"], q["step"]) for q in quiz["questions"]] == [(0, "step one"), (1, "step two")]
    assert all("correct_answer" not in q for q in quiz["questions"])


def test_all_correct_ends_without_reteaching(fake_llm):
    _, config = run()

    values, quiz = answer(config, ["right", " right "])  # stray whitespace still counts

    assert quiz is None
    assert [a.is_correct for a in values["grader"][0].answers] == [True, True]
    assert ReteachResult not in fake_llm.calls
    assert graph.get_state(config).next == ()


def test_missed_step_is_retaught_and_requizzed(fake_llm):
    _, config = run()

    values, quiz = answer(config, ["right", "wrong 2"])

    graded = values["grader"][0]
    assert [(a.index, a.picked, a.is_correct) for a in graded.answers] == [(0, "right", True), (1, "wrong 2", False)]
    assert fake_llm.calls.count(ReteachResult) == 1
    [retaught] = values["reteacher"]
    assert (retaught.index, retaught.round, retaught.step) == (1, 1, "step two")
    assert retaught.misconception == "thinks wrong 2"
    assert quiz["round"] == 2
    assert [(q["index"], q["question"]) for q in quiz["questions"]] == [(1, "retry question about step two?")]


def test_each_step_is_retaught_at_most_twice(fake_llm):
    _, config = run()

    answer(config, ["wrong 1", "right"])
    answer(config, ["wrong 1"])
    values, quiz = answer(config, ["wrong 3"])

    assert quiz is None  # out of retries: the run ends with the step still missed
    assert [r.round for r in values["reteacher"]] == [1, 2]
    assert [g.answers[0].is_correct for g in values["grader"]] == [False, False, False]
    assert fake_llm.calls.count(ReteachResult) == 2


def test_second_reteach_sees_the_first(fake_llm, monkeypatch):
    _, config = run()
    contents = []

    def spy(system, content, schema):
        contents.append(content)
        return fake_llm(system, content, schema)

    monkeypatch.setattr("tutor.llm.structured", spy)
    answer(config, ["right", "wrong 1"])
    answer(config, ["wrong 2"])

    assert "earlier re-explanation" not in contents[0]
    assert "An earlier re-explanation that still didn't land:\nanother look at step two" in contents[1]
    assert "Student picked: wrong 2" in contents[1]


def test_teachers_run_in_parallel(fake_llm):
    fake_llm.steps = ["a", "b", "c"]
    # each teacher blocks until all 3 are waiting; if they ran one at a time the barrier would time out
    fake_llm.teacher_barrier = threading.Barrier(3, timeout=2)

    (values, _), _ = run()

    assert [t.step for t in taught_in_order(values)] == ["a", "b", "c"]


def test_plan_with_no_steps_skips_teacher_review_and_quiz(fake_llm):
    fake_llm.steps = []

    (values, quiz), _ = run()

    assert fake_llm.calls == [IntakeResult, PlannerResult]
    assert values.get("teacher", []) == []
    assert "reviewer" not in values
    assert quiz is None


def test_image_only_made_when_teacher_asks_for_one(fake_image):
    (values, _), _ = run()

    first, second = taught_in_order(values)
    assert first.image == "fake.png"
    assert second.image is None
    assert fake_image.prompts == ["diagram of step one"]


def test_failed_image_does_not_stop_the_lesson(fake_image, capsys):
    fake_image.error = RuntimeError("image model down")

    (values, _), _ = run()

    assert len(values["teacher"]) == 2
    assert taught_in_order(values)[0].image is None
    assert "Image generation failed for step 1" in capsys.readouterr().out
