"""Orchestrate EasyTutor topic evaluation and content generation."""

import asyncio
import json
import logging
import os
from pathlib import Path

from llm.evaluator import ContentEvaluator, TagEvaluator, TopicEvaluator
from llm.exporter import attach_generation_cost, export_approved_topic, is_topic_exported, missing_translation_languages
from llm.generator import ContentGenerator, ImageGenerator, TagGenerator, TopicGenerator
from llm.metrics import OpenRouterCostMeter
from llm.translator import Translator
from llm.util import (
    AgentHelper,
    BROAD_TAGS,
    TOPICS_FILE,
    add_specific_tag,
    normalize_topic,
    read_approved_content,
    read_cached_topic_items,
    read_content,
    read_evaluations,
    read_generated_image,
    read_specific_tags,
    read_used_topic_values,
    write_approved_content,
    write_content,
    write_evaluations,
    write_generated_image,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


class EasyTutorAgent:
    CONTEXT = """
    you are a tech educator specialising in tech education for elderly, poor and
    the usually tech marginalised people in society. you do not teach  advanced
    levels or concepts. your mission is always enabling marginalised sections on
    the basics of emerging technologies in very simple terms and descriptions,
    so that the students can later on themselves get deeper into any topic if
    they are interested. The goal is to ensure that marginalised groups do not
    get left behind in key technologies which affect the society and are often
    needed for personal needs. E.g. using internet, using smart phones, using
    messenger apps, using websites, placing online orders, using google.
    """

    def __init__(self):
        logger.info("Initializing EasyTutorAgent")

        self._topic_generator = TopicGenerator(
            context=self.CONTEXT,
            models={
                "Z.ai: GLM 5.2": "z-ai/glm-5.2",
                "DeepSeek V4 Flash 0731": "deepseek/deepseek-v4-flash-0731",
                "OpenAI: GPT-5.6 Luna": "openai/gpt-5.6-luna",
            })
        self._content_generator = ContentGenerator(
            context=self.CONTEXT,
            models={
                "Z.ai: GLM 5.2": "z-ai/glm-5.2",
                "OpenAI: GPT-5.6 Luna": "openai/gpt-5.6-luna",
            })
        self._tag_generator = TagGenerator(
            context=self.CONTEXT,
            broad_tags=BROAD_TAGS,
            models={"Z.ai: GLM 5.2": "z-ai/glm-5.2"}
        )
        self._image_generator = ImageGenerator(
            context=self.CONTEXT,

            models={"Google: Nano Banana 2 Lite": "google/gemini-3.1-flash-lite-image"},
            # models={"Recraft: Recraft V4.1 Utility Pro": "recraft/recraft-v4.1-utility-pro"},
            # models={"Recraft: Recraft V4 Vector": "recraft/recraft-v4-vector"},

            output_dir=Path(__file__).resolve().parents[1] / "web" / "public" / "images",
        )
        self._translator = Translator(
            context=self.CONTEXT,

            models={"DeepSeek: DeepSeek V4 Flash 0423": "deepseek/deepseek-v4-flash"},
            # models={"Z.ai: GLM 5.2": "z-ai/glm-5.2"},

            prefix="Lesson Translator",
        )

        self._topic_evaluator = TopicEvaluator(
            context=self.CONTEXT,
            models={"MoonshotAI: Kimi K3": "moonshotai/kimi-k3"})
        self._content_evaluator = ContentEvaluator(
            context=self.CONTEXT,
            models={"MoonshotAI: Kimi K3": "moonshotai/kimi-k3"})
        self._tag_evaluator = TagEvaluator(
            context=self.CONTEXT,
            models={"MoonshotAI: Kimi K3": "moonshotai/kimi-k3"})

    @staticmethod
    def _load_json_object(output: str, source: str) -> dict:
        text = output.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            logger.warning("%s returned invalid JSON: %r", source, text[:500])
            raise ValueError(f"{source} returned invalid JSON") from error

        if not isinstance(data, dict):
            raise ValueError(f"{source} returned a JSON value instead of an object")
        return data

    async def _rank_topics(
        self,
        main_topic: str,
        topic_items: list[tuple[str, str]],
        meter: OpenRouterCostMeter | None = None,
    ) -> None:
        topics_to_rank = "\n".join(
            f"{index}. {topic}"
            for index, (_, topic) in enumerate(topic_items)
        )
        eval_message = f"""
        Rank the following sub-topics for the main topic {main_topic}.

        {topics_to_rank}
        """
        eval_results = await self._topic_evaluator.evaluate(
            message=eval_message,
            trace="EasyTutor: Topic Evaluation",
            meter=meter,
            stage="topic_evaluation",
        )

        try:
            existing_evaluations = read_evaluations(TOPICS_FILE, main_topic)
        except FileNotFoundError:
            existing_evaluations = {}

        normalized_eval_results = {}
        for eval_key, eval_output in eval_results.items():
            eval_json = json.loads(eval_output)
            ranked_indices = eval_json["result"]
            reason = eval_json.get("reason", "")
            reason = "\n".join(str(item) for item in reason) if isinstance(reason, list) else str(reason)

            if not isinstance(ranked_indices, list):
                raise ValueError(
                    f"Evaluator {eval_key!r} returned a non-ranking result: {ranked_indices!r}"
                )

            normalized_result = {}
            for index in ranked_indices:
                model, topic = topic_items[index]
                normalized_result[topic] = model

            normalized_eval_results[eval_key] = {
                "result": normalized_result,
                "reason": reason,
                "used": existing_evaluations.get(eval_key, {}).get("used", []),
            }

        write_evaluations(TOPICS_FILE, main_topic, normalized_eval_results)
        print(normalized_eval_results)

    def _get_next_topic(self, main_topic: str) -> tuple[str, str] | None:
        try:
            topic_items = read_cached_topic_items(TOPICS_FILE, main_topic)
        except FileNotFoundError:
            return None
        return topic_items[0] if topic_items else None

    def _remove_used_topic(self, main_topic: str, topic: str) -> None:
        evaluations = read_evaluations(TOPICS_FILE, main_topic)
        evaluator_model, latest_evaluation = next(iter(evaluations.items()))
        if latest_evaluation["result"].pop(topic, None) is not None:
            latest_evaluation.setdefault("used", []).append(topic)
        write_evaluations(TOPICS_FILE, main_topic, {evaluator_model: latest_evaluation})
        logger.info("Removed used topic '%s' from the topic cache", topic)

    async def generate_topics(self, main_topic: str, meter: OpenRouterCostMeter | None = None) -> None:
        cached_topic_items = []
        try:
            cached_topic_items = read_cached_topic_items(TOPICS_FILE, main_topic)
            cached_topics = [topic for _, topic in cached_topic_items]
            used_topics = read_used_topic_values(TOPICS_FILE, main_topic)
        except FileNotFoundError:
            logger.info("No existing topics file found at %s", TOPICS_FILE)
            cached_topics = []
            used_topics = []
        except json.JSONDecodeError as error:
            logger.info("Could not parse topics file; generating new topics: %s", error)
            cached_topics = []
            used_topics = []
        except (PermissionError, OSError) as error:
            logger.info("Error reading topics file: %s", error)
            cached_topics = []
            used_topics = []

        all_existing_topics = cached_topics + used_topics
        existing_topics = "\n".join(f"- {topic}" for topic in all_existing_topics)
        topic_prompt = f"Suggest a topic for {main_topic}"
        if existing_topics:
            topic_prompt = f"""
            Suggest a topic for {main_topic}

            Do not suggest any of these already-used topics:
            {existing_topics}
            """

        topic_results = await self._topic_generator.generate(
            message=topic_prompt,
            trace="EasyTutor: Topic Generation",
            meter=meter,
            stage="topic_generation",
        )
        existing_topic_set = {normalize_topic(topic) for topic in all_existing_topics}
        unique_topic_results = {
            model: topic
            for model, topic in topic_results.items()
            if normalize_topic(topic) not in existing_topic_set
        }
        skipped_count = len(topic_results) - len(unique_topic_results)
        if skipped_count:
            logger.info("Skipped %d repeated generated topics", skipped_count)
        if not unique_topic_results:
            logger.info("No new unique topics were generated")
            if meter:
                meter.mark_stage("topic_evaluation", "skipped")
            return

        logger.info("New topics generated: %s", unique_topic_results)
        all_topic_items = cached_topic_items + list(unique_topic_results.items())
        await self._rank_topics(main_topic, all_topic_items, meter)

    async def _select_content(
        self,
        topic: str,
        content_results: dict[str, str],
        meter: OpenRouterCostMeter | None = None,
    ) -> str:
        content_items = list(content_results.items())
        contents_to_rank = "\n\n".join(
            f"{index}. {content}"
            for index, (_, content) in enumerate(content_items)
        )
        eval_results = await self._content_evaluator.evaluate(
            message=f"""
            Rank the following content drafts for the topic: {topic}

            {contents_to_rank}
            """,
            trace="EasyTutor: Content Evaluation",
            meter=meter,
            stage="content_evaluation",
        )

        if not eval_results:
            raise ValueError("Content evaluator did not return any results")

        evaluator_name, eval_output = next(iter(eval_results.items()))
        ranked_indices = json.loads(eval_output)["result"]
        if not isinstance(ranked_indices, list) or not ranked_indices:
            raise ValueError(
                f"Content evaluator {evaluator_name!r} returned no ranking: {ranked_indices!r}"
            )

        selected_index = ranked_indices[0]
        if not isinstance(selected_index, int) or not 0 <= selected_index < len(content_items):
            raise ValueError(
                f"Content evaluator {evaluator_name!r} returned an invalid index: {selected_index!r}"
            )

        selected_model, _ = content_items[selected_index]
        logger.info(
            "Selected content for topic '%s' from model '%s' using evaluator '%s'",
            topic,
            selected_model,
            evaluator_name,
        )
        return selected_model

    async def _select_specific_tag(
        self,
        candidate: str,
        existing_tags: list[str],
        meter: OpenRouterCostMeter | None = None,
    ) -> str:
        if not existing_tags:
            add_specific_tag(candidate)
            if meter:
                meter.mark_stage("tag_evaluation", "skipped")
            return candidate

        existing_by_name = {tag.casefold(): tag for tag in existing_tags}
        if candidate.casefold() in existing_by_name:
            if meter:
                meter.mark_stage("tag_evaluation", "skipped")
            return existing_by_name[candidate.casefold()]

        tag_options = [*existing_tags, candidate]
        tag_options_text = "\n".join(
            f"{index}. {tag}"
            for index, tag in enumerate(tag_options)
        )
        eval_results = await self._tag_evaluator.evaluate(
            message=f"""
            Proposed subject tag: {candidate}

            Choose the canonical tag from these options:
            {tag_options_text}
            """,
            trace="EasyTutor: Tag Evaluation",
            meter=meter,
            stage="tag_evaluation",
        )
        if not eval_results:
            raise ValueError("Tag evaluator did not return any results")

        evaluator_name, eval_output = next(iter(eval_results.items()))
        ranked_indices = json.loads(eval_output)["result"]
        if not isinstance(ranked_indices, list) or len(ranked_indices) != 1:
            raise ValueError(
                f"Tag evaluator {evaluator_name!r} returned an invalid ranking: {ranked_indices!r}"
            )

        selected_index = ranked_indices[0]
        if not isinstance(selected_index, int) or not 0 <= selected_index < len(tag_options):
            raise ValueError(
                f"Tag evaluator {evaluator_name!r} returned an invalid index: {selected_index!r}"
            )

        selected_tag = tag_options[selected_index]
        if selected_tag == candidate:
            add_specific_tag(candidate)
        return selected_tag

    async def _generate_tags(
        self,
        topic: str,
        content: str,
        meter: OpenRouterCostMeter | None = None,
    ) -> list[str]:
        existing_tags = read_specific_tags()
        existing_tags_text = "\n".join(f"- {tag}" for tag in existing_tags) or "- None yet"
        tag_message = f"""
        Lesson topic: {topic}

        Lesson content:
        {content}

        Existing subject tags:
        {existing_tags_text}
        """
        tag_data = None
        generator_name = "unknown"
        for attempt in range(2):
            tag_results = await self._tag_generator.generate(
                message=tag_message,
                trace="EasyTutor: Tag Generation",
                meter=meter,
                stage="tag_generation",
            )
            if not tag_results:
                raise ValueError("Tag generator did not return any results")

            generator_name, tag_output = next(iter(tag_results.items()))
            try:
                tag_data = self._load_json_object(tag_output, f"Tag generator {generator_name!r}")
                break
            except ValueError:
                if attempt == 0:
                    logger.info("Retrying tag generation for topic '%s'", topic)
                    continue
                raise

        if tag_data is None:
            raise ValueError("Tag generator did not return a usable result")
        categories = tag_data.get("categories")
        if (
            not isinstance(categories, list)
            or not 1 <= len(categories) <= 2
            or len(set(categories)) != len(categories)
            or any(not isinstance(category, str) or category not in BROAD_TAGS for category in categories)
        ):
            raise ValueError(
                f"Tag generator {generator_name!r} returned invalid categories: {categories!r}"
            )

        specific_tag = tag_data.get("specificTag")
        if specific_tag is None:
            return categories
        if not isinstance(specific_tag, str):
            raise ValueError(
                f"Tag generator {generator_name!r} returned an invalid subject tag: {specific_tag!r}"
            )

        specific_tag = " ".join(specific_tag.split())
        broad_tags_by_name = {tag.casefold() for tag in BROAD_TAGS}
        if (
            not specific_tag
            or len(specific_tag) > 48
            or specific_tag.casefold() in broad_tags_by_name
        ):
            raise ValueError(
                f"Tag generator {generator_name!r} returned an invalid subject tag: {specific_tag!r}"
            )

        canonical_tag = await self._select_specific_tag(specific_tag, existing_tags, meter)
        return [*categories, canonical_tag]

    async def _generate_article(
        self,
        main_topic: str,
        topic: str,
        meter: OpenRouterCostMeter | None = None,
    ) -> None:
        # 1. Generate content for sub-topic.
        cached_content = read_content(topic)
        content_models = self._content_generator.models()
        if all(content_model in cached_content for content_model in content_models):
            logger.info("Using complete content cache for topic '%s'", topic)
            content_results = {
                content_model: cached_content[content_model]
                for content_model in content_models
            }
            if meter:
                meter.mark_stage("content_generation", "cached")
        else:
            logger.info(f"Generating content for topic {topic}")
            content_results = await self._content_generator.generate(
                message=f"""
                Generate content for topic: {topic}
                """,
                trace="EasyTutor: Content Generation",
                meter=meter,
                stage="content_generation",
            )
            write_content(topic, content_results)

        # 2. Evaluate and pick one content.
        approval = read_approved_content(topic)
        if approval is None:
            selected_model = await self._select_content(topic, content_results, meter)
            tags = await self._generate_tags(topic, content_results[selected_model], meter)
            write_approved_content(topic, selected_model, tags)
            approval = {"model": selected_model, "tags": tags}
        else:
            logger.info("Using approved content cache for topic '%s'", topic)
            selected_model = approval.get("model")
            if not isinstance(selected_model, str) or selected_model not in content_results:
                raise ValueError(f"Approved model for topic {topic!r} is unavailable")
            if meter:
                meter.mark_stage("content_evaluation", "cached")
                meter.mark_stage("tag_generation", "cached")
                meter.mark_stage("tag_evaluation", "cached")

        # 3. Generate image/diagram from the selected Markdown before exporting it.
        image = read_generated_image(topic)
        if image is None:
            generated_image = await self._image_generator.generate(
                topic=topic,
                content=content_results[selected_model],
                meter=meter,
            )
            write_generated_image(
                topic=topic,
                path=generated_image.path,
                alt_text=generated_image.alt_text,
                model=generated_image.model,
                media_type=generated_image.media_type,
                width=generated_image.width,
                height=generated_image.height,
            )
            image = read_generated_image(topic)
        else:
            logger.info("Using generated image cache for topic '%s'", topic)
            if meter:
                meter.mark_stage("image_generation", "cached")
        if image is None:
            raise ValueError(f"Could not read generated image metadata for topic {topic!r}")

        # 3. Translate and export. The translated Markdown files are the
        # published translation records; no JSON cache is needed or written.
        if is_topic_exported(topic):
            logger.info("Using exported Markdown cache for topic '%s'", topic)
            if meter:
                for language in self._translator.languages():
                    meter.mark_stage(f"translation_{language}", "cached")
        else:
            missing_languages = missing_translation_languages(topic)
            translation_results = await self._translator.generate(
                message=(
                    f"{content_results[selected_model].strip()}\n\n"
                    f"<!-- saral-tags: {json.dumps(approval['tags'], ensure_ascii=False)} -->\n"
                    f"<!-- saral-image-alt: {image['altText']} -->"
                ),
                trace="EasyTutor: Translation",
                languages=missing_languages,
                meter=meter,
            )
            if meter:
                for language in self._translator.languages():
                    if language not in missing_languages:
                        meter.mark_stage(f"translation_{language}", "cached")
            translator_models = tuple(self._translator.models())
            if len(translator_models) != 1:
                raise ValueError(
                    "Translation export needs exactly one translation model until a translation evaluator is added"
                )
            translator_model = translator_models[0]
            translations = {
                language: results[translator_model]
                for language, results in translation_results.items()
            }
            outputs = export_approved_topic(topic, translations)
            logger.info("Exported topic '%s' to %s", topic, ", ".join(map(str, outputs)))

        self._remove_used_topic(main_topic, topic)

        # 4. Check if publishing is completed.

    async def _finish_meter(
        self,
        meter: OpenRouterCostMeter,
        error: BaseException | None = None,
    ) -> dict[str, object] | None:
        try:
            report = await meter.finish(api_key=AgentHelper.openrouter_api_key(), error=error)
        except Exception:
            # Metering is observability, not a publishing prerequisite. A
            # completed lesson must remain successful even if reporting fails.
            logger.exception("Could not write the cost report")
            return None
        else:
            logger.info("Wrote cost report to %s", report)
            return meter.display_cost() if error is None and meter.kind == "article" else None

    async def run(self, generate_subtopic=False) -> None:
        logger.info("Starting EasyTutorAgent run")
        main_topic = "Teaching AI"

        if generate_subtopic:
            meter = OpenRouterCostMeter(
                kind="topic_generation",
                trigger="topic_generation",
                main_topic=main_topic,
                run_id=os.getenv("SARAL_COST_RUN_ID"),
            )
            try:
                await self.generate_topics(main_topic, meter)
            except BaseException as error:
                await self._finish_meter(meter, error)
                raise
            await self._finish_meter(meter)
        else:
            # 1. Get next sub-topic
            next_topic = self._get_next_topic(main_topic)
            if next_topic is None:
                logger.info("No ranked topics remain; please re-run with -gt")
            else:
                sub_topic = next_topic[1]
                logger.info(f"Using cached next top-ranked topic '{sub_topic}'")
                metadata = {
                    key.removeprefix("SARAL_").lower(): value
                    for key, value in os.environ.items()
                    if key in {"SARAL_RERUN_BATCH_ID", "SARAL_RERUN_OPTIONS"}
                }
                meter = OpenRouterCostMeter(
                    kind="article",
                    trigger=os.getenv("SARAL_RUN_TRIGGER", "normal"),
                    main_topic=main_topic,
                    topic=sub_topic,
                    run_id=os.getenv("SARAL_COST_RUN_ID"),
                    metadata=metadata,
                )
                try:
                    await self._generate_article(main_topic, sub_topic, meter)
                except BaseException as error:
                    await self._finish_meter(meter, error)
                    raise
                display_cost = await self._finish_meter(meter)
                if display_cost is not None:
                    try:
                        output = attach_generation_cost(sub_topic, display_cost)
                    except Exception:
                        # The local audit report remains available even if the
                        # public Markdown metadata cannot be updated.
                        logger.exception("Could not attach cost data to the exported article")
                    else:
                        logger.info("Attached latest cost data to %s", output)

        logger.info("Finished EasyTutorAgent run")

    def _publish(self):
        # Create git commit after checking the files being added to the commit
        # Git push with appropriate comment.
        # Wait for some time and then fetch https://saralai-seven.vercel.app/
        # and check the title of the latest article and match it with the last
        # generated article.

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--generate_subtopic', '-gt', action='store_true', help='Generate sub-topic')
    args = parser.parse_args()

    asyncio.run(EasyTutorAgent().run(args.generate_subtopic))
