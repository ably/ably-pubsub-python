import glob
import os
import tokenize as std_tokenize

import tokenize_rt

rename_classes = [
    "AblyRest",
    "Push",
    "PushAdmin",
    "Channel",
    "Channels",
    "Auth",
    "Http",
    "PaginatedResult",
    "HttpPaginatedResponse"
]

_TOKEN_REPLACE = {
    "__aenter__": "__enter__",
    "__aexit__": "__exit__",
    "__aiter__": "__iter__",
    "__anext__": "__next__",
    "asynccontextmanager": "contextmanager",
    "AsyncIterable": "Iterable",
    "AsyncIterator": "Iterator",
    "AsyncGenerator": "Generator",
    "StopAsyncIteration": "StopIteration",
}

_IMPORTS_REPLACE = {
}

_STRING_REPLACE = {
}

_CLASS_RENAME = {
}


class Rule:
    """A single set of rules for 'unasync'ing file(s)"""

    def __init__(self, fromdir, todir, output_file_prefix="", additional_replacements=None):
        self.fromdir = fromdir.replace("/", os.sep)
        self.todir = todir.replace("/", os.sep)
        self.ouput_file_prefix = output_file_prefix

        # Add any additional user-defined token replacements to our list.
        self.token_replacements = _TOKEN_REPLACE.copy()
        for key, val in (additional_replacements or {}).items():
            self.token_replacements[key] = val

    def _match(self, filepath):
        """Determines if a Rule matches a given filepath and if so
        returns a higher comparable value if the match is more specific.
        """
        file_segments = [x for x in filepath.split(os.sep) if x]
        from_segments = [x for x in self.fromdir.split(os.sep) if x]
        len_from_segments = len(from_segments)

        if len_from_segments > len(file_segments):
            return False

        for i in range(len(file_segments) - len_from_segments + 1):
            if file_segments[i: i + len_from_segments] == from_segments:
                return len_from_segments, i

        return False

    def _unasync_file(self, filepath):
        with open(filepath, "rb") as f:
            encoding, _ = std_tokenize.detect_encoding(f.readline)

        with open(filepath, encoding=encoding) as f:
            tokens = tokenize_rt.src_to_tokens(f.read())
            tokens = self._unasync_tokens(tokens)
            result = tokenize_rt.tokens_to_src(tokens)
            new_file_path = os.path.join(os.path.dirname(filepath),
                                         self.ouput_file_prefix + os.path.basename(filepath))
            outfilepath = new_file_path.replace(self.fromdir, self.todir)
            os.makedirs(os.path.dirname(outfilepath), exist_ok=True)
            with open(outfilepath, "wb") as f:
                f.write(result.encode(encoding))

    def _unasync_tokens(self, tokens: list):
        new_tokens = []
        token_counter = 0
        async_await_block_started = False
        async_await_char_diff = -6  # (len("async") or len("await") is 6)
        async_await_offset = 0

        renamed_class_call_started = False
        renamed_class_char_diff = 0
        renamed_class_offset = 0

        while token_counter < len(tokens):
            token = tokens[token_counter]

            if async_await_block_started or renamed_class_call_started:
                # Fix indentation issues for async/await fn definition/call
                if token.src == '\n':
                    new_tokens.append(token)
                    token_counter = token_counter + 1
                    next_newline_token = tokens[token_counter]
                    new_tab_src = next_newline_token.src

                    if (renamed_class_call_started and
                            tokens[token_counter + 1].utf8_byte_offset >= renamed_class_offset):
                        if renamed_class_char_diff < 0:
                            new_tab_src = new_tab_src[:renamed_class_char_diff]
                        else:
                            new_tab_src = new_tab_src + renamed_class_char_diff * " "

                    if (async_await_block_started and len(next_newline_token.src) >= 6 and
                            tokens[token_counter + 1].utf8_byte_offset >= async_await_offset + 6):
                        new_tab_src = new_tab_src[:async_await_char_diff]  # remove last 6 white spaces

                    next_newline_token = next_newline_token._replace(src=new_tab_src)
                    new_tokens.append(next_newline_token)
                    token_counter = token_counter + 1
                    continue

            if token.src == ')':
                async_await_block_started = False
                async_await_offset = 0
                renamed_class_call_started = False
                renamed_class_char_diff = 0

            if token.src in ["async", "await"]:
                # When removing async or await, we want to skip the following whitespace
                token_counter = token_counter + 2
                is_async_start = tokens[token_counter].src == 'def'
                is_await_start = False
                for i in range(token_counter, token_counter + 6):
                    if tokens[i].src == '(':
                        is_await_start = True
                        break
                if is_async_start or is_await_start:
                    # Fix indentation issues for async/await fn definition/call
                    async_await_offset = token.utf8_byte_offset
                    async_await_block_started = True
                continue

            elif token.name == "NAME":
                if token.src == "from":
                    if tokens[token_counter + 1].src == " ":
                        token_counter = self._replace_import(tokens, token_counter, new_tokens)
                        continue
                else:
                    token_new_src = self._unasync_name(token.src)
                    if token.src == token_new_src:
                        token_new_src = self._class_rename(token.src)
                        if token.src != token_new_src:
                            renamed_class_offset = token.utf8_byte_offset
                            renamed_class_char_diff = len(token_new_src) - len(token.src)
                            for i in range(token_counter, token_counter + 6):
                                if tokens[i].src == '(':
                                    renamed_class_call_started = True
                                    break

                    token = token._replace(src=token_new_src)
            elif token.name == "STRING":
                src_token = token.src.replace("'", "")
                if _STRING_REPLACE.get(src_token) is not None:
                    new_token = f"'{_STRING_REPLACE[src_token]}'"
                    token = token._replace(src=new_token)
                else:
                    src_token = token.src.replace("\"", "")
                    if _STRING_REPLACE.get(src_token) is not None:
                        new_token = f"\"{_STRING_REPLACE[src_token]}\""
                        token = token._replace(src=new_token)

            new_tokens.append(token)
            token_counter = token_counter + 1

        return new_tokens

    def _replace_import(self, tokens, token_counter, new_tokens: list):
        new_tokens.append(tokens[token_counter])
        new_tokens.append(tokens[token_counter + 1])

        full_lib_name = ''
        lib_name_counter = token_counter + 2
        if len(_IMPORTS_REPLACE.keys()) == 0:
            return lib_name_counter

        while True:
            if tokens[lib_name_counter].src == " ":
                break
            full_lib_name = full_lib_name + tokens[lib_name_counter].src
            lib_name_counter = lib_name_counter + 1

        for key, value in _IMPORTS_REPLACE.items():
            if key in full_lib_name:
                updated_lib_name = full_lib_name.replace(key, value)
                for lib_name_part in updated_lib_name.split("."):
                    lib_name_part = self._class_rename(lib_name_part)
                    new_tokens.append(tokenize_rt.Token("NAME", lib_name_part))
                    new_tokens.append(tokenize_rt.Token("OP", "."))
                new_tokens.pop()
                return lib_name_counter

        lib_name_counter = token_counter + 2
        return lib_name_counter

    def _class_rename(self, name):
        if name in _CLASS_RENAME:
            return _CLASS_RENAME[name]
        return name

    def _unasync_name(self, name):
        if name in self.token_replacements:
            return self.token_replacements[name]
        return name


def unasync_files(fpath_list, rules):
    for f in fpath_list:
        found_rule = None
        found_weight = None

        for rule in rules:
            weight = rule._match(f)
            if weight and (found_weight is None or weight > found_weight):
                found_rule = rule
                found_weight = weight

        if found_rule:
            found_rule._unasync_file(f)


def find_files(dir_path, file_name_regex):
    return glob.glob(os.path.join(dir_path, "**", file_name_regex), recursive=True)


def run():
    # Source files ==========================================

    _TOKEN_REPLACE["AsyncClient"] = "Client"
    _TOKEN_REPLACE["aclose"] = "close"
    _TOKEN_REPLACE["assert_waiter"] = "assert_waiter_sync"

    # Ordering matters: _replace_import takes the first key that is a substring
    # of the imported module, and the sync flavour of the public surface lives
    # at ably.pubsub.server.sync rather than under ably.pubsub.sync.
    _IMPORTS_REPLACE["ably.pubsub.server"] = "ably.pubsub.server.sync"
    _IMPORTS_REPLACE["ably.pubsub"] = "ably.pubsub.sync"

    # here...
    for class_name in rename_classes:
        _CLASS_RENAME[class_name] = f"{class_name}Sync"

    _STRING_REPLACE["Auth"] = "AuthSync"
    # The sync flavour's factory lives in ably.pubsub.server.sync. There is no
    # sync realtime factory, so create_realtime_client is left pointing at the
    # asynchronous one, which is the right advice for that case.
    _STRING_REPLACE['ably.pubsub.server.create_http_client'] = \
        'ably.pubsub.server.sync.create_http_client'

    src_dir_path = os.path.join(os.getcwd(), "ably", "pubsub")
    dest_dir_path = os.path.join(os.getcwd(), "ably", "pubsub", "sync")
    # ably/pubsub/server is the hand-written public re-export surface; its
    # synchronous flavour lives in ably/pubsub/server/sync.py, not under sync/.
    server_dir_path = os.path.join(os.getcwd(), "ably", "pubsub", "server")

    relevant_src_files = (set(find_files(src_dir_path, "*.py")) -
                          set(find_files(dest_dir_path, "*.py")) -
                          set(find_files(server_dir_path, "*.py")))

    unasync_files(list(relevant_src_files), [Rule(fromdir=src_dir_path, todir=dest_dir_path)])

    # Test files ==============================================

    _TOKEN_REPLACE["asyncSetUp"] = "setUp"
    _TOKEN_REPLACE["asyncTearDown"] = "tearDown"
    _TOKEN_REPLACE["AsyncMock"] = "Mock"

    _TOKEN_REPLACE["_Channel__publish_request_body"] = "_ChannelSync__publish_request_body"
    _TOKEN_REPLACE["_Http__client"] = "_HttpSync__client"

    _IMPORTS_REPLACE["test.ably"] = "test.ably.sync"

    _STRING_REPLACE['/../assets/testAppSpec.json'] = '/../../assets/testAppSpec.json'
    _STRING_REPLACE['ably.pubsub.rest.auth.Auth.request_token'] = \
        'ably.pubsub.sync.rest.auth.AuthSync.request_token'
    _STRING_REPLACE['ably.pubsub.rest.auth.TokenRequest'] = 'ably.pubsub.sync.rest.auth.TokenRequest'
    _STRING_REPLACE['ably.pubsub.rest.rest.Http.post'] = 'ably.pubsub.sync.rest.rest.HttpSync.post'
    _STRING_REPLACE['httpx.AsyncClient.send'] = 'httpx.Client.send'
    _STRING_REPLACE['ably.pubsub.util.exceptions.AblyException.raise_for_response'] = \
        'ably.pubsub.sync.util.exceptions.AblyException.raise_for_response'
    _STRING_REPLACE['ably.pubsub.rest.rest.AblyRest.time'] = 'ably.pubsub.sync.rest.rest.AblyRestSync.time'
    _STRING_REPLACE['ably.pubsub.rest.auth.Auth._timestamp'] = 'ably.pubsub.sync.rest.auth.AuthSync._timestamp'

    # round 1
    src_dir_path = os.path.join(os.getcwd(), "test", "ably")
    dest_dir_path = os.path.join(os.getcwd(), "test", "ably", "sync")
    src_files = [os.path.join(os.getcwd(), "test", "ably", "testapp.py"),
                 os.path.join(os.getcwd(), "test", "ably", "utils.py")]

    unasync_files(src_files, [Rule(fromdir=src_dir_path, todir=dest_dir_path)])

    # round 2
    src_dir_path = os.path.join(os.getcwd(), "test", "ably", "rest")
    dest_dir_path = os.path.join(os.getcwd(), "test", "ably", "sync", "rest")
    src_files = find_files(src_dir_path, "*.py")

    unasync_files(src_files, [Rule(fromdir=src_dir_path, todir=dest_dir_path, output_file_prefix="sync_")])
