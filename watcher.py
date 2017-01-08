#!/usr/bin/python3
import time

from src.regression import *

import smtplib


from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart


def mail(subject,mail_to, body='',mail_from='tom.barbette@ulg.ac.be', images=[]):
    print(subject)
    COMMASPACE = ', '

    # Create the container (outer) email message.
    msg = MIMEMultipart()
    msg['Subject'] = subject

    if (mail_from):
        msg['From'] = mail_from
    msg['To'] = COMMASPACE.join(mail_to)
    msg.preamble = body


    for img in images:
        img = MIMEImage(img)
        msg.attach(img)

    s = smtplib.SMTP('localhost')
    s.send_message(msg)
    s.quit()


def main():
    parser = argparse.ArgumentParser(description='Click Watcher')
    parser.add_argument('repos', metavar='repo name', type=str, nargs='+', help='names of the repositories to watch');
    parser.add_argument('--interval', metavar='secs', type=int, nargs=1, default=60,
                        help='interval in seconds between polling of repositories');
    parser.add_argument('--history', dest='history', metavar='N', type=int, default=0,
                        help='assume last N commits as untested (default 0)');
    parser.add_argument('--tags', metavar='tag', type=str, nargs='+', help='list of tags');
    parser.add_argument('--testie', metavar='path or testie', type=str, nargs='?', default='tests',
                        help='script or script folder. Default is tests');
    parser.add_argument('--quiet', help='Quiet mode', dest='quiet', action='store_true', default=False)
    parser.set_defaults(tags=[])
    args = parser.parse_args();
    history = args.history

    mail_to = ['tom.barbette@ulg.ac.be']

    repo_list = []
    for repo_name in args.repos:
        repo = Repository(repo_name)
        tags = args.tags
        tags += repo.tags
        gitrepo = repo.checkout()
        last_build = None
        for i, commit in enumerate(gitrepo.iter_commits('origin/' + repo.branch)):
            last_build = Build(repo, commit.hexsha[:7])
            if last_build.hasResults():
                if history == 0:
                    break
                else:
                    history -= 1
            if i > 100:
                last_build = None
                break
        if last_build != None:
            print("[%s] Last tested uuid is %s" % (repo.name, last_build.uuid))
        repo.last_build = last_build

        testies = Testie.expandFolder(args.testie, tags=tags, quiet=args.quiet)
        repo_list.append((repo, testies))

    terminate = False
    while not terminate:
        for repo, testies in repo_list:
            gitrepo = repo.gitrepo()
            commit = next(gitrepo.iter_commits('origin/' + repo.branch))
            uuid = commit.hexsha[:7]
            if repo.last_build and uuid == repo.last_build.uuid:
                if not args.quiet:
                    print("[%s] No new uuid !" % (repo.name))
                continue

            print("[%s] New uuid %s !" % (repo.name, uuid))
            build = Build(repo, uuid)

            graphs = []

            if not build.build_if_needed():
                mail("[%s] Could not compile %s !" % (repo.name, uuid),mail_to=mail_to)
                continue
            nok = 0
            for testie in testies:
                print("[%s] Running testie %s..." % (repo.name, testie.filename))
                regression = Regression(testie)
                if repo.last_build:
                    old_all_results = repo.last_build.readUuid(testie)
                else:
                    old_all_results = None
                all_results = testie.execute_all(build)
                ok = regression.compare(testie.variables, all_results, build, old_all_results, repo.last_build) == 0
                if ok:
                    nok += 1
                else:
                    print("[%s] Testie %s FAILED !" % (repo.name, testie.filename))
                build.writeUuid(testie, all_results)

                grapher = Grapher()
                graphs_series = [(testie, build, all_results)]
                if repo.last_build:
                    graphs_series.append((testie, repo.last_build, old_all_results))
                g = grapher.graph(series=graphs_series, title=testie.get_title(),
                              filename=None, graph_variables=testie.variables)
                graphs.append(g)
            build.writeResults()
            repo.last_build = build
            body = ''
            mail("[%s] Finished run for %s, %d/%d tests passed" % (repo.name, uuid, nok, len(testies)), body=body,mail_to=mail_to, images=graphs)

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
