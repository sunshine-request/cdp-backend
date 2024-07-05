#!/usr/bin/env python

import argparse
import logging
import sys
import traceback
from pathlib import Path

from fsspec.core import url_to_fs
from fsspec.implementations.local import LocalFileSystem

#PRC Added
import fireo

from cdp_backend.database.models import File, Event, Session, Transcript, IndexedEventGram
#PRC Added

#PRC Edited
from cdp_backend.file_store.functions import remove_remote_file
# from cdp_backend.pipeline import event_gather_pipeline as pipeline
# from cdp_backend.pipeline.ingestion_models import EventIngestionModel
# from cdp_backend.pipeline.pipeline_config import EventGatherPipelineConfig

###############################################################################

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)4s: %(module)s:%(lineno)4s %(asctime)s] %(message)s",
)
log = logging.getLogger(__name__)

###############################################################################


class Args(argparse.Namespace):
    def __init__(self) -> None:
        self.__parse()

    def __parse(self) -> None:
        p = argparse.ArgumentParser(
            prog="delete_cdp_event",
            description="Delete existing event from Firestore + GCS "
            + "(including sessions, minutes, votes).",
        )

        p.add_argument(
            "--google_credentials_file",
            type=Path,
            help="Path to Google service account JSON key.",
        )

        p.add_argument(
            "--event_key",
            type=str,
            help="Key of event, can be copied from browser window.",
        )

        p.add_argument(
            '--dry-run', 
            action=argparse.BooleanOptionalAction,
            help="Whether to actually change datastore and filesystem .",
        )

        p.parse_args(namespace=self)


def delete_event(google_creds_path: Path, event_key: str) -> None:
    log.info("Delete event...")

    # Good test event to delete = 031f001d0d87

    # Connect to database
    fireo.connection(from_file=google_creds_path)


    # Implement logic to do: 
    # for each session related to the event
    #     delete the transcripts for each session (and the files in storage)
    #     delete thumbnail file references (and the files in storage)
    #     delete the event body (if it isn't used by any other event)
    #     for each event minutes items related to the event
    #         delete the referenced minutes item if it isn't used in any other event
    #         delete the referenced matter if it isn't used in any other event
    #         delete all the matter files if matter / minutes item was used in any other event
    #         delete all event minutes item files
    #         delete any matter status updates that are referenced to the event minutes item
    #         for each vote related to the event minutes item:
    #             delete any people (and their roles) that do not have votes on any other event
    #             delete the picture file in db and the stored picture file
    #             for each role:
    #                 delete the seat if it is not used by any other person
    #                 delete the seat image ref and the store image file from storage
    #             delete any votes that link to the event / event minutes item
    #         delete the event minutes item itself
    #     delete any indexed event grams linked to event
    #     delete any matter sponsers for matter refs OR people that no longer exist after all of the above
    #     delete the event itself

    # Fetch all sessions
    event = Event.collection.get(f"event/{event_key}")

    if(not event):
        print("No event found")
        return
    
    # Fetch all sessions for event
    sessions = Session.collection.filter(event_ref=event.key).fetch()
    sessions = list(sessions)

    print("Sessions")
    print(len(sessions))
    for session in sessions:
        print("Session Key")
        print(session.key)
        print("Session Content Hash")
        print(session.session_content_hash)        

        transcripts = Transcript.collection.filter(session_ref=session.key).fetch()
        transcripts = list(transcripts)

        for transcript in transcripts:
            # Check Generator
            print(transcript.generator)

            # if(not transcript.generator.startswith("CDP WebVTT Conversion")):
                # print("Not a WebVTT Event, DO NOT DELETE")
                # exit()


            if(transcript.file_ref):
                try:
                    transcript_file = transcript.file_ref.get()
                    print("Transcript")
                    print(transcript_file.id)
                    print(transcript_file.uri)
                    print(transcript_file.name)
                    print(transcript_file.description)
                    print(transcript_file.media_type)

                    other_transcripts = File.collection.filter(name=transcript_file.name).fetch()
                    other_transcripts = list(other_transcripts)

                    if len(other_transcripts) <= 1:
                        print("Remove Transcript file")
                        remove_remote_file(google_creds_path, transcript_file.uri)
                    else:
                        print("File used by other File documents, skip deletion")

                    File.collection.delete(transcript_file.key)
                # Handle file not found
                except BaseException as e:
                    log.error(f"Error: {str(e)}")



            Transcript.collection.delete(transcript.key)

        # TODO: Before deleting files, check if any other sessions use this file
        # Note this also applies to thumbnails etc
        other_sessions = Session.collection.filter(session_content_hash=session.session_content_hash).fetch()
        other_sessions = list(other_sessions)
        print("Other Sessions")
        print(other_sessions)
        print(len(other_sessions))

        if len(other_sessions) <= 1:
            print("Delete session files")
            # Also try to delete the common file names
            common_files = ["-audio.err", "-audio.out", "-audio.wav", "-hover-thumbnail.gif", "-static-thumbnail.png"]

            for suffix in common_files:
                try:
                    print(f"Try to remove gs://cdp-asheville-ektqmrjs.appspot.com/{session.session_content_hash}{suffix}")
                    remove_remote_file(google_creds_path, f"gs://cdp-asheville-ektqmrjs.appspot.com/{session.session_content_hash}{suffix}")
                except:
                    pass

        Session.collection.delete(session.key)

    print("CHECK STATIC THUMBNAIL")
    print(event.static_thumbnail_ref)

    if(event.static_thumbnail_ref):
        print("HERE in static thumbnail")
        try:
            thumbnail = event.static_thumbnail_ref.get()

            #TODO: CHECK IF THIS FILE IS USED BY OTHER EVENTS
            other_events = Event.collection.filter(static_thumbnail_ref=thumbnail.key).fetch()
            other_events = list(other_events)
            print("Static thumbnail other events")
            print(other_events)
            print(len(other_events))

            if len(other_events) <= 1:
                print("Delete Static Thumbnail")
                remove_remote_file(google_creds_path, thumbnail.uri)
            else:
                print("File used by other events, skip deletion")

            File.collection.delete(thumbnail.key)

        # Handle file not found
        except BaseException as e:
            log.error(f"Error: {str(e)}")

    print("CHECK HOVER THUMBNAIL")
    print(event.hover_thumbnail_ref)

    if(event.hover_thumbnail_ref):
        try:
            thumbnail = event.hover_thumbnail_ref.get()

            #TODO: CHECK IF THIS FILE IS USED BY OTHER EVENTS
            other_events = Event.collection.filter(hover_thumbnail_ref=thumbnail.key).fetch()
            other_events = list(other_events)
            print("Hover thumbnail other events")
            print(other_events)
            print(len(other_events))

            if len(other_events) <= 1:
                print("Delete Hover Thumbnail")
                remove_remote_file(google_creds_path, thumbnail.uri)
            else:
                print("File used by other events, skip deletion")

            File.collection.delete(thumbnail.key)

        except BaseException as e:
            log.error(f"Error: {str(e)}")


    if(event.body_ref):
        body = event.body_ref.get()
        # print(body.id)
        print(body.name, body.description)

        print("BODY EVENTS")
        body_events = Event.collection.filter(body_ref=body.key).fetch()

        print(len(list(body_events)))

        # TODO - CHECK FOR RELATED Roles

        if(len(list(body_events)) == 1):
            print("Deleting body")
            print(body.id)
            print(body.name, body.description)
            # Body.collection.delete(body.key)


    #     delete any indexed event grams linked to event
    index_grams = IndexedEventGram.collection.filter(event_ref=event.key).fetch()
    index_grams = list(index_grams)
    print(f"Found {len(index_grams)} index grams")

    index_gram_key_list = []
    for index_gram in index_grams:
        index_gram_key_list.append(index_gram.key)

    IndexedEventGram.collection.delete_all(index_gram_key_list)

    Event.collection.delete(event.key)
    print("Event Deleted")


###############################################################################

if __name__ == "__main__":
    try:
        args = Args()
        delete_event(
            google_creds_path=args.google_credentials_file,
            event_key=args.event_key
        )
    except Exception as e:
        log.error("=============================================")
        log.error("\n\n" + traceback.format_exc())
        log.error("=============================================")
        log.error("\n\n" + str(e) + "\n")
        log.error("=============================================")
        sys.exit(1)
