# FastAPI Async Server Proof of Concept

This is a small proof-of-concept project I slapped together to figure out how to
get [FastAPI](https://fastapi.tiangolo.com/) and Python's
[Async IO](https://docs.python.org/3/library/asyncio.html) working together to
asynchronously write the body of an API request to a file.


## Premise & Design

The key idea I wanted to test was leveraging Async I/O on both the network side
(reading the body of the HTTP request) AND on the filesystem side (writing the
contents of the request to a file) _without_ those two waiting operations being
mutually exclusive. In other words, the most throughput can be achieved when we
are able to wait on both reading and writing I/O operations _at the same time_.

To achieve this, I've used two co-routines: one for request-reading and
another for file-writing co-routine, rather than have these two operations in a
single co-routine that's doing one or the other at any point in time. 
A bounded, async `Queue` is used to pass chunks of data from the reading coro to
the writing coro.

In practice, this design will end up read-bound or write-bound in most 
situations (see 'Testing' below). However, what it prevents is having the 
next read be waiting on the completion of the write.

Visually, here is what a single co-routine's waiting may theoretically look 
like if it were read-bound (assuming negligible CPU time):

```text
|------ Waiting for read ------|- Waiting for write -|------ Waiting for read ------|- Waiting for write -|
```

And here is what the 2 co-routine approach can theoretically do instead:

```text
|------ Waiting for read ------|------ Waiting for read ------|------ Waiting for read ------|
                               |- Waiting for write -|        |- Waiting for write -|        |- Waiting for write -|
```


## Requirements

* MacOS (or Linux should work, too)
* Python 3.10+


## Setup 

```bin/setup```

This sets up the Python virtual environment under `venv/` and creates a 
large-ish file of random text called `random.txt`.


## Run 

```bin/run```

Starts the server using `uvicorn` (with automatic reload).


## Testing

This command should upload a file of random text to the server:

```curl --data-binary @random.txt http://127.0.0.1:8000/file```       

The output shows what the request-reading co-routine is doing on the left, and
what the file-writing co-routine is doing on the left.
Each time the context switches co-routines, a newline is started.

When running both the server and `curl` on localhost, the output should show
that the event thread becomes write-bound.
You can see this below, because the writing co-routine (RHS) always context 
switches while `await`ing on `write()`, while the reading co-routine (LHS)
always switches while `await`ing to `put()` on the size-bound queue.

```text
49470: Starting -> stream().next() -> put() -> stream().next() -> put() -> stream().next() -> put() -> stream().next() -> put() 
                                                -> get() -> write() 
-> stream().next() -> put() 
                                                -> task_done() -> get() -> write() 
-> stream().next() -> put() 
                                                -> task_done() -> get() -> write() 
-> stream().next() -> put() 
                                                -> task_done() -> get() -> write() 
-> stream().next() -> join()

                                                -> task_done() -> get() -> write() -> task_done() -> get() -> write() -> task_done() -> get() -> write() -> task_done() -> get() -> cancel()
49470: Done
```

We can simulate what would happen over a slower network connection with 
something like:

```curl --limit-rate 50K --data-binary @random.txt http://127.0.0.1:8000/file```    

When running this, the output shows that the event thread becomes read-bound.
Below you'll see the writing co-routine (RHS) context switches while `await`ing 
on `get()` on the queue, while the reading co-routine (LHS) is now switching 
while `await`ing on request stream's `next()`.

```text
50938: Starting -> stream().next() -> put() -> stream().next() 
                                                -> get() -> write() -> task_done() -> get() 
-> put() -> stream().next() 
                                                -> write() -> task_done() -> get() 
-> put() -> stream().next() 
                                                -> write() -> task_done() -> get() 
-> put() -> stream().next() 
...
-> put() -> stream().next() 
                                                -> write() -> task_done() -> get() 
-> put() -> stream().next() -> put() -> stream().next() -> join()

                                                -> write() -> task_done() -> get() -> write() -> task_done() -> get() -> cancel()
50938: Done

```

## License

The code in this repository is shared under the `The Unlicense`.

See [LICENSE] for more information.

