//#define Py_LIMITED_API

extern int printf(const char*, ...);
#include <assert.h>
#include <stdlib.h>
#include <Python.h>
#include <structmember.h>

//TODO
#define Py_Assert(x) assert(x)

static PyObject* pystring_child = NULL;
static PyObject* pystring_finish = NULL;
static PyObject* pystring_module = NULL;
static PyObject* pystring_relationship = NULL;
static PyObject* pystring_run_background = NULL;
static PyObject* pystring_sibling = NULL;
static PyObject* pystring_thread = NULL;
static PyObject* pystring_timeout = NULL;

typedef struct
{
	PyObject_HEAD
	PyObject *contexts[32];
	size_t context_length;
	PyObject *next_timeout;
} Chain;

typedef struct
{
	PyObject_HEAD
	Chain *chain;
	size_t from, to;
} ChainIter;

static PyObject* ChainIter_new(PyTypeObject *const type, PyObject *const args, PyObject *const kwds);
static void ChainIter_dealloc(ChainIter *const self);
static PyObject* ChainIter_iter(ChainIter *const self);
static ChainIter* Chain_iter_from_to(Chain *const self, size_t from, size_t to);
static PyObject* ChainIter_next(ChainIter *const self);

static PyTypeObject ChainIterType = {
	PyVarObject_HEAD_INIT(NULL, 0)
	"ChainIter",                   /* tp_name */
	sizeof(ChainIter),             /* tp_basicsize */
	0,                             /* tp_itemsize */
	(destructor)ChainIter_dealloc, /* tp_dealloc */
	0,                             /* tp_print */
	0,                             /* tp_getattr */
	0,                             /* tp_setattr */
	0,                             /* tp_reserved */
	0,                             /* tp_repr */
	0,                             /* tp_as_number */
	0,                             /* tp_as_sequence */
	0,                             /* tp_as_mapping */
	0,                             /* tp_hash  */
	0,                             /* tp_call */
	0,                             /* tp_str */
	0,                             /* tp_getattro */
	0,                             /* tp_setattro */
	0,                             /* tp_as_buffer */
	Py_TPFLAGS_DEFAULT,            /* tp_flags */
	NULL,
	0,                             /* tp_traverse */
	0,                             /* tp_clear */
	0,                             /* tp_richcompare */
	0,                             /* tp_weaklistoffset */
	(getiterfunc)ChainIter_iter,   /* tp_iter */
	(iternextfunc)ChainIter_next,  /* tp_iternext */
	0,                             /* tp_methods */
	NULL,                          /* tp_members */
	NULL,                          /* tp_getset */
	0,                             /* tp_base */
	0,                             /* tp_dict */
	0,                             /* tp_descr_get */
	0,                             /* tp_descr_set */
	0,                             /* tp_dictoffset */
	0,                             /* tp_init*/
	0,                             /* tp_alloc */
	ChainIter_new,                 /* tp_new */
};

static PyObject*
get_context(void)
{
	static PyObject *Context = NULL;
	if(Context) {
		return Context;
	}

	PyObject *const ContextModule = PyImport_ImportModule("schedsi.cpu.context");
	if(!ContextModule) {
		return NULL;
	}
	Context = PyObject_GetAttrString(ContextModule, "Context");
	Py_DECREF(ContextModule);
	if(!Context) {
		return NULL;
	}
	return Context;
}

static PyObject* Chain_new(PyTypeObject *const type, PyObject *const args, PyObject *const kwds);
static void Chain_dealloc(Chain *const self);
static int Chain_init(Chain *const self, PyObject *const args, PyObject *const kwds) __attribute__((unused));
static PyObject* Chain_from_context(PyTypeObject *const type, PyObject *const start);
static PyObject* Chain_from_thread(PyTypeObject *const type, PyObject *const thread);
static Py_ssize_t Chain_len(Chain *const self);
static PyObject* Chain_current_context(Chain *const self, void *const);
static PyObject* Chain_contexts(Chain *const self, void *const);
static PyObject* Chain_bottom(Chain *const self, void *const);
static PyObject* Chain_top(Chain *const self, void *const);
static PyObject* Chain_parent(Chain *const self, void *const);
static PyObject* Chain_thread_at(Chain *const self, PyObject *const idx);
static int Chain_update_timeout(Chain *const self);
static PyObject* Chain_append_chain(Chain *const self, PyObject *const tail);
static PyObject* Chain_set_timer(Chain *const self, PyObject *const args);
static PyObject* Chain_elapse(Chain *const self, PyObject *const time);
static PyObject* Chain_find_elapsed_timer(Chain *const self);
static PyObject* Chain_split(Chain *const self, PyObject *const split_idx);
static PyObject* Chain_finish(Chain *const self, PyObject *const current_time);
static PyObject* Chain_run_background(Chain *const self, PyObject *const args);
static PyObject* Chain_iter(Chain *const self);

static PyObject* Chain_dict_encode(Chain *const self, PyObject *const args);

static PyMethodDef Chain_methods[] = {
	{"from_context", (PyCFunction)Chain_from_context, METH_CLASS | METH_O,
	 "Create a :class:`Chain` with a single context."
	},
	{"from_thread", (PyCFunction)Chain_from_thread, METH_CLASS | METH_O,
	 "Create a :class:`Chain` with a new context for `start`."
	},
	{"thread_at", (PyCFunction)Chain_thread_at, METH_O,
	 "Return the thread at index `idx` in the chain.\n"
	 "\n"
	 "Negative values are treated as an offset from the back."
	},
//if we enable this, we also need to Py_XDECREF(self->next_timeout)!
#if 0
	{"_update_timeout", Chain_update_timeout, METH_NOARGS,
	 "Return the length of the :class:`Chain`.\n"
	 "\n"
	 "Find the lowest timeout in the chain and set :attr:`next_timeout`."
	},
#endif
	{"append_chain", (PyCFunction)Chain_append_chain, METH_O,
	 "Append a :class:`Chain`."
	},
	{"set_timer", (PyCFunction)Chain_set_timer, METH_VARARGS,
	 "Set the timeout of a context in the chain."
	 "\n"
	 "If `idx` is not specified the current (top) context is used."
	},
	{"elapse", (PyCFunction)Chain_elapse, METH_O,
	 "Elapse all timers in the chain.\n"
	 "\n"
	 "Must not be called if a timeout in the chain has elapsed."
	},
	{"find_elapsed_timer", (PyCFunction)Chain_find_elapsed_timer, METH_NOARGS,
	 "Return the index of the first elapsed timer in the :class:`Chain`."
	},
	{"split", (PyCFunction)Chain_split, METH_O,
	 "Split the :class:`Chain` in two at `idx`.\n"
	 "\n"
	 "The instance keeps the chain up to and excluding `idx`.\n"
	 "\n"
	 "Returns the tail :class:`Chain`."
	},
	{"finish", (PyCFunction)Chain_finish, METH_O,
	 "Call :meth:`Thread.finish <schedsi.threads.Thread.finish>`"
	 "on every :class:`~schedsi.threads.Thread` in the :class:`Chain`."
	},
	{"run_background", (PyCFunction)Chain_run_background, METH_VARARGS,
	 "Call :meth:`Thread.run_background <schedsi.threads.Thread.run_background>`"
	 "on every :class:`~schedsi.threads.Thread` in the :class:`Chain`"
	 "except :attr:`current_context`."
	},
	{"dict_encode", (PyCFunction)Chain_dict_encode, METH_VARARGS,
	 "TODO",
	},
	{NULL}
};

static PyMemberDef Chain_members[] = {
	{"next_timeout", T_OBJECT_EX, offsetof(Chain, next_timeout), 0,
	 NULL
	},
	{NULL}
};

static PyGetSetDef Chain_properties[] = {
	{"current_context", (getter)Chain_current_context, NULL,
	 "The current (top) context.",
	 NULL
	},
	{"contexts", (getter)Chain_contexts, NULL,
	 "An iterator over all contexts.",
	 NULL
	},
	{"bottom", (getter)Chain_bottom, NULL,
	 "The bottom thread.",
	 NULL
	},
	{"top", (getter)Chain_top, NULL,
	 "The top thread.",
	 NULL
	},
	{"parent", (getter)Chain_parent, NULL,
	 "The parent thread.",
	 NULL
	},
	{NULL}
};

static PySequenceMethods Chain_sequence_methods = {
	(lenfunc)Chain_len,
};

static PyTypeObject ChainType = {
	PyVarObject_HEAD_INIT(NULL, 0)
	"Chain",                   /* tp_name */
	sizeof(Chain),             /* tp_basicsize */
	0,                         /* tp_itemsize */
	(destructor)Chain_dealloc, /* tp_dealloc */
	0,                         /* tp_print */
	0,                         /* tp_getattr */
	0,                         /* tp_setattr */
	0,                         /* tp_reserved */
	0,                         /* tp_repr */
	0,                         /* tp_as_number */
	&Chain_sequence_methods,   /* tp_as_sequence */
	0,                         /* tp_as_mapping */
	0,                         /* tp_hash  */
	0,                         /* tp_call */
	0,                         /* tp_str */
	0,                         /* tp_getattro */
	0,                         /* tp_setattro */
	0,                         /* tp_as_buffer */
	Py_TPFLAGS_DEFAULT,        /* tp_flags */
	"The contexts for a scheduling-chain.\n"
	"\n"
	"The context chain represents the stack of contexts for a scheduling-chain.\n"
	"It may be a partial chain, i.e. the bottom is not the kernel.",
	0,                         /* tp_traverse */
	0,                         /* tp_clear */
	0,                         /* tp_richcompare */
	0,                         /* tp_weaklistoffset */
	(getiterfunc)Chain_iter,   /* tp_iter */
	0,                         /* tp_iternext */
	Chain_methods,             /* tp_methods */
	Chain_members,             /* tp_members */
	Chain_properties,          /* tp_getset */
	0,                         /* tp_base */
	0,                         /* tp_dict */
	0,                         /* tp_descr_get */
	0,                         /* tp_descr_set */
	0,                         /* tp_dictoffset */
	0, //(initproc)Chain_init, /* tp_init */
	0,                         /* tp_alloc */
	Chain_new,                 /* tp_new */
};

static PyObject*
Chain_new(PyTypeObject *const type, PyObject *const args, PyObject *const kwds)
{
	assert(type);
	Chain *const self = (Chain*)type->tp_alloc(type, 0);
	if(!self) {
		return NULL;
	}

#ifndef NDEBUG
	memset(self->contexts, 0, sizeof(self->contexts));
#endif
	self->context_length = 0;
	self->next_timeout = NULL;

	return (PyObject*)self;
}

static void
Chain_dealloc(Chain *const self)
{
	assert(self);
	for(size_t i = 0; i < self->context_length; ++i) {
		Py_DECREF(self->contexts[i]);
	}

	Py_TYPE(self)->tp_free((PyObject*)self);
}

static int
Chain_init(Chain *const self, PyObject *const args, PyObject *const kwds)
{
	assert(self);
	assert(args && kwds);
	PyObject *chain;
	static char *kwlist[] = { "chain", NULL };
	if(!PyArg_ParseTupleAndKeywords(args, kwds, "$O", kwlist, &chain)) {
		assert(PyErr_Occurred());
		return -1;
	}
	assert(chain);

	self->contexts[0] = chain;
	Py_INCREF(self->contexts[0]);
	assert(self->context_length == 0);
	self->context_length = 1;
	self->next_timeout = PyObject_GetAttr(self->contexts[0], pystring_timeout);
	if(!self->next_timeout) {
		assert(PyErr_Occurred());
		Chain_dealloc(self);
		return -1;
	}

	return 0;
}

//"Create a :class:`Chain` with a single context."
//@classmethod
static PyObject*
Chain_from_context(PyTypeObject *const type, PyObject *const start)
{
	assert(start);
	Chain *const self = (Chain*)Chain_new(type, NULL, NULL);
	if(!self) {
		assert(PyErr_Occurred());
		return NULL;
	}

	PyObject *const timeout = PyObject_GetAttr(start, pystring_timeout);
	if(!timeout) {
		assert(PyErr_Occurred());
		Chain_dealloc(self);
		return NULL;
	}

	self->contexts[0] = start;
	Py_INCREF(self->contexts[0]);
	self->context_length = 1;
	self->next_timeout = timeout;

	return (PyObject*)self;
}

//"Create a :class:`Chain` with a new context for `start`."
//@classmethod
static PyObject*
Chain_from_thread(PyTypeObject *const type, PyObject *const thread)
{
	assert(thread);
	assert(get_context());
	PyObject *const context = PyObject_CallFunctionObjArgs(get_context(), thread, NULL);
	if(!context) {
		assert(PyErr_Occurred());
		return NULL;
	}
	PyObject *const self = Chain_from_context(type, context);
	Py_DECREF(context);
	if(!self) {
		assert(PyErr_Occurred());
		return NULL;
	}
	return self;
}

//"Return the length of the :class:`Chain`."
static Py_ssize_t
Chain_len(Chain *const self)
{
	assert(self);
	return self->context_length;
}

//"The current (top) context."
//@property
static PyObject*
Chain_current_context(Chain *const self, void *const arg)
{
	assert(self);
	assert(!arg);
	PyObject *const ctx = self->context_length ? self->contexts[self->context_length - 1] : Py_None;
	Py_INCREF(ctx);
	return ctx;
}

//"An iterator over all contexts."
//@property
static PyObject*
Chain_contexts(Chain *const self, void *const arg)
{
	assert(self);
	assert(!arg);
	return Chain_iter(self);
}

//"The bottom thread."
//@property
static PyObject*
Chain_bottom(Chain *const self, void *const arg)
{
	assert(self);
	assert(!arg);
	if(self->context_length == 0) {
		PyErr_SetString(PyExc_IndexError, "index out of range");
		return NULL;
	}
	PyObject *const thread = PyObject_GetAttr(self->contexts[0], pystring_thread);
	if(!thread) {
		assert(PyErr_Occurred());
		return NULL;
	}
	return thread;
}

//"The top thread."
//@property
static PyObject*
Chain_top(Chain *const self, void *const arg)
{
	assert(self);
	assert(!arg);
	if(self->context_length == 0) {
		PyErr_SetString(PyExc_IndexError, "index out of range");
		return NULL;
	}
	PyObject *const thread = PyObject_GetAttr(self->contexts[self->context_length - 1], pystring_thread);
	if(!thread) {
		assert(PyErr_Occurred());
		return NULL;
	}
	return thread;
}

//"The parent thread."
//@property
static PyObject*
Chain_parent(Chain *const self, void *const arg)
{
	assert(self);
	assert(!arg);
	if(self->context_length < 2) {
		Py_RETURN_NONE;
	}
	PyObject *const thread = PyObject_GetAttr(self->contexts[self->context_length - 2], pystring_thread);
	if(!thread) {
		assert(PyErr_Occurred());
		return NULL;
	}
	return thread;
}

static int
Chain_absolute_index(Chain *self, ssize_t *const idx)
{
	if(PyErr_Occurred()) {
		return 0;
	}

	if(*idx < 0) {
		*idx += self->context_length;
	}
	if(*idx < 0) {
		PyErr_SetString(PyExc_IndexError, "index out of range");
		return 0;
	}
	if(*idx >= (ssize_t)self->context_length) {
		PyErr_SetString(PyExc_IndexError, "index out of range");
		return 0;
	}

	return 1;
}

//"Return the thread at index `idx` in the chain.
//Negative values are treated as an offset from the back."
static PyObject*
Chain_thread_at(Chain *const self, PyObject *const idx)
{
	assert(self);
	assert(idx);
	ssize_t index = PyLong_AsSsize_t(idx);
	if(!Chain_absolute_index(self, &index)) {
		return NULL;
	}

	PyObject *const thread = PyObject_GetAttr(self->contexts[index], pystring_thread);
	if(!thread) {
		assert(PyErr_Occurred());
		return NULL;
	}
	return thread;
}

//"Find the lowest timeout in the chain and set :attr:`next_timeout`."
static int
Chain_update_timeout(Chain *const self)
{
	assert(self);
	assert(!self->next_timeout);
	for(size_t i = 0; i < self->context_length; ++i) {
		PyObject *const ctx_timeout = PyObject_GetAttr(self->contexts[i], pystring_timeout);
		if(!ctx_timeout) {
			assert(PyErr_Occurred());
			break;
		}
		if(ctx_timeout == Py_None) {
			Py_DECREF(ctx_timeout);
			continue;
		}
		if(!self->next_timeout) {
			self->next_timeout = ctx_timeout;
			continue;
		}
		const int cmp = PyObject_RichCompareBool(ctx_timeout, self->next_timeout, Py_LT);
		if(cmp == 1) {
			self->next_timeout = ctx_timeout;
			continue;
		}
		Py_DECREF(ctx_timeout);
		if(PyErr_Occurred()) {
			break;
		}
		assert(cmp != -1);
	}
	if(!self->next_timeout) {
		self->next_timeout = Py_None;
		Py_INCREF(self->next_timeout);
	}
	if(PyErr_Occurred()) {
		return 0;
	}
	return 1;
}

//"Append a :class:`Chain`."
static PyObject*
Chain_append_chain(Chain *const self, PyObject *const tail_obj)
{
	assert(self);
	assert(tail_obj);
	if(PyObject_IsInstance(tail_obj, (PyObject*)&ChainType) != 1) {
		if(!PyErr_Occurred()) {
			PyErr_SetString(PyExc_TypeError, "expected Chain");
		}
		return NULL;
	}
	Chain *tail = (Chain*)tail_obj;
	const size_t append_idx = self->context_length;
	memcpy(&self->contexts[self->context_length], tail->contexts, tail->context_length * sizeof(*self->contexts));
	self->context_length += tail->context_length;

	//we only need to keep the bottom
#if 0
	for(size_t i = 0; i < tail->context_length; ++i) {
		Py_INCREF(tail->contexts[i]);
	}
#endif
	tail->contexts[0] = tail->contexts[tail->context_length - 1];
	Py_INCREF(tail->contexts[0]);
#ifndef NDEBUG
	memset(&tail->contexts[1], 0, (tail->context_length - 1) * sizeof(*tail->contexts));
#endif
	tail->context_length = 1;

	//check for new timeout
	const int cmp = PyObject_RichCompareBool(tail->next_timeout, self->next_timeout, Py_LT);
	if(cmp == -1) {
		if(tail->next_timeout != Py_None && self->next_timeout != Py_None) {
			assert(PyErr_Occurred());
			return NULL;
		}
		PyErr_Clear();
	}
	if(cmp == 1 || self->next_timeout == Py_None) {
		Py_DECREF(self->next_timeout);
		self->next_timeout = tail->next_timeout;
		Py_INCREF(self->next_timeout);
	}

	ChainIter *const iter = Chain_iter_from_to(self, append_idx, self->context_length);
	if(!iter) {
		assert(PyErr_Occurred());
		return NULL;
	}
	return (PyObject*)iter;
}

//"Set the timeout of a context in the chain.
//If `idx` is not specified the current (top) context is used."
static PyObject*
Chain_set_timer(Chain *const self, PyObject *const args)
{
	PyObject *timeout;
	ssize_t idx = (ssize_t)self->context_length - 1;
	PyArg_ParseTuple(args, "O|n", &timeout, &idx);
	if(!Chain_absolute_index(self, &idx)) {
		assert(PyErr_Occurred());
		return NULL;
	}

	PyObject *const prev_time = PyObject_GetAttr(self->contexts[idx], pystring_timeout);
	if(!prev_time) {
		assert(PyErr_Occurred());
		return NULL;
	}
	if(PyObject_SetAttr(self->contexts[idx], pystring_timeout, timeout) != 0) {
		assert(PyErr_Occurred());
		goto err;
	}
	if(self->next_timeout == Py_None) {
		Py_DECREF(self->next_timeout);
		self->next_timeout = timeout;
		Py_INCREF(self->next_timeout);
		Py_RETURN_NONE;
	}
	if(timeout != Py_None)
	{
		const int cmp = PyObject_RichCompareBool(self->next_timeout, timeout, Py_GE);
		if(cmp == -1) {
			assert(PyErr_Occurred());
			goto err;
		}
		if(cmp == 1) {
			Py_DECREF(self->next_timeout);
			self->next_timeout = timeout;
			Py_INCREF(self->next_timeout);
			Py_RETURN_NONE;
		}
	}
	if(prev_time != Py_None) {
		const int cmp = PyObject_RichCompareBool(prev_time, self->next_timeout, Py_EQ);
		if(cmp == -1) {
			assert(PyErr_Occurred());
			goto err;
		}
		if(cmp == 1) {
			Py_DECREF(self->next_timeout);
			self->next_timeout = NULL;
			if(!Chain_update_timeout(self)) {
				assert(PyErr_Occurred());
				goto err;
			}
		}
	}

err:
	Py_DECREF(prev_time);
	if(PyErr_Occurred()) {
		return NULL;
	}
	Py_RETURN_NONE;
}

//"Elapse all timers in the chain.
//Must not be called if a timeout in the chain has elapsed."
static PyObject*
Chain_elapse(Chain *const self, PyObject *const time)
{
	assert(self);
	assert(time);

	PyErr_Clear();
	PyObject* py_zero = PyLong_FromLong(0);
	if(self->next_timeout == Py_None || PyObject_RichCompareBool(time, py_zero, Py_EQ) == 1) {
		//no time to count down then
		Py_RETURN_NONE;
	}
	Py_Assert(self->context_length);

	for(size_t i = 0; i < self->context_length; ++i) {
		PyObject *timeout = PyObject_GetAttr(self->contexts[i], pystring_timeout);
		if(!timeout) {
			assert(PyErr_Occurred());
			break;
		}
		if(timeout != Py_None) {
			int done = PyObject_RichCompareBool(timeout, py_zero, Py_LE);
			assert(done != -1);
			const int cmp = PyObject_RichCompareBool(timeout, self->next_timeout, Py_EQ);
			if(cmp == -1) {
				assert(PyErr_Occurred());
				return NULL;
			}
			Py_Assert(!done || cmp);
			PyObject *const new_timeout = PyNumber_InPlaceSubtract(timeout, time);
			if(!new_timeout) {
				assert(PyErr_Occurred());
				Py_DECREF(timeout);
				return NULL;
			}
			if(self->next_timeout == timeout) {
				Py_DECREF(self->next_timeout);
				self->next_timeout = new_timeout;
				Py_INCREF(self->next_timeout);
			}
			if(PyObject_SetAttr(self->contexts[i], pystring_timeout, new_timeout) != 0) {
				assert(PyErr_Occurred());
				Py_DECREF(new_timeout);
				return NULL;
			}
			//Py_DECREF(new_timeout);
			if(done) {
				break;
			}
		}
		Py_DECREF(timeout);
	}
	Py_RETURN_NONE;
}

static PyObject*
Chain_find_elapsed_timer(Chain *const self)
{
	assert(self);
	for(size_t i = 0; i < self->context_length; ++i) {
		PyObject *const timeout = PyObject_GetAttr(self->contexts[i], pystring_timeout);
		if(!timeout) {
			assert(PyErr_Occurred());
			return NULL;
		}
		Py_DECREF(timeout);
		if(timeout == Py_None) {
			continue;
		}
		const int cmp = PyObject_RichCompareBool(timeout, PyLong_FromLong(0), Py_LE);
		if(cmp == -1) {
			assert(PyErr_Occurred());
			return NULL;
		}
		if(cmp) {
			return PyLong_FromSize_t(i);
		}
	}
	PyErr_SetString(PyExc_IndexError, "index out of bounds");
	return NULL;
}

//"Split the :class:`Chain` in two at `idx`.
//The instance keeps the chain up to and excluding `idx`.
//Returns the tail :class:`Chain`."
static PyObject*
Chain_split(Chain *const self, PyObject *const split_idx)
{
	assert(self);
	assert(split_idx);

	ssize_t idx = PyLong_AsSsize_t(split_idx);
	if(!Chain_absolute_index(self, &idx)) {
		return NULL;
	}

	Chain *const tail = (Chain*)Chain_new(&ChainType, NULL, NULL);
	//FIXME: if(!tail)

	tail->context_length = self->context_length - idx;
	memcpy(tail->contexts, &self->contexts[idx], tail->context_length * sizeof(*tail->contexts));
	self->context_length = idx;
#ifndef NDEBUG
	memset(&self->contexts[idx], 0, tail->context_length * sizeof(*self->contexts));
#endif

	//TODO: optimization here?
	Py_DECREF(self->next_timeout);
	tail->next_timeout = NULL;
	if(!Chain_update_timeout(tail)) {
		assert(PyErr_Occurred());
		return NULL;
	}
	Py_DECREF(self->next_timeout);
	self->next_timeout = NULL;
	if(!Chain_update_timeout(self)) {
		assert(PyErr_Occurred());
		return NULL;
	}
	assert(!PyErr_Occurred());

	return (PyObject*)tail;
}

static PyObject*
Chain_finish(Chain *const self, PyObject *const current_time)
{
	assert(self);
	assert(current_time);
	for(size_t i = 0; i < self->context_length; ++i) {
		PyObject *const thread = PyObject_GetAttr(self->contexts[i], pystring_thread);
		if(!thread) {
			assert(PyErr_Occurred());
			return NULL;
		}
		PyObject *const finish = PyObject_GetAttr(thread, pystring_finish);
		Py_DECREF(thread);
		if(!finish) {
			assert(PyErr_Occurred());
			return NULL;
		}
		PyObject *const result = PyObject_CallFunctionObjArgs(finish, current_time, NULL);
		Py_DECREF(finish);
		if(!result) {
			assert(PyErr_Occurred());
			return NULL;
		}
		Py_DECREF(result);
	}
	Py_RETURN_NONE;
}

static PyObject*
Chain_run_background(Chain *const self, PyObject *const args)
{
	assert(self);
	assert(args);
	if(self->context_length == 0) {
		Py_RETURN_NONE;
	}
	PyObject *current_time, *time;
	if(!PyArg_ParseTuple(args, "OO", &current_time, &time)) {
		assert(PyErr_Occurred());
		return NULL;
	}
	assert(!PyErr_Occurred());
	for(size_t i = 0; i < self->context_length - 1; ++i) {
		PyObject *const thread = PyObject_GetAttr(self->contexts[i], pystring_thread);
		if(!thread) {
			assert(PyErr_Occurred());
			return NULL;
		}
		PyObject *const run_background = PyObject_GetAttr(thread, pystring_run_background);
		Py_DECREF(thread);
		if(!run_background) {
			assert(PyErr_Occurred());
			return NULL;
		}
		PyObject *const result = PyObject_CallFunctionObjArgs(run_background, current_time, time, NULL);
		Py_DECREF(run_background);
		if(!result) {
			assert(PyErr_Occurred());
			return NULL;
		}
		Py_DECREF(result);
	}
	Py_RETURN_NONE;
}

static PyObject*
Chain_dict_encode(Chain *const appendix, PyObject *const args)
{
	assert(appendix);
	assert(args);
	//TODO: error handling
	PyObject *current_context, *thread_encoder;
	PyArg_ParseTuple(args, "OO", &current_context, &thread_encoder);

	PyObject *chain = PyTuple_New(appendix->context_length);

	PyObject *first_thread = PyObject_GetAttr(appendix->contexts[0], pystring_thread);
	PyObject *first_module = PyObject_GetAttr(first_thread, pystring_module);
	PyObject *current_thread = PyObject_GetAttr(current_context, pystring_thread);
	PyObject *current_module = PyObject_GetAttr(current_thread, pystring_module);
	Py_DECREF(current_thread);

	PyObject *elem = PyDict_New();
	PyDict_SetItem(elem, pystring_thread, PyObject_CallFunctionObjArgs(thread_encoder, first_thread, NULL));
	Py_DECREF(first_thread);
	PyDict_SetItem(elem, pystring_relationship, first_module == current_module ? pystring_sibling : pystring_child);
	PyTuple_SET_ITEM(chain, 0, elem);
	Py_DECREF(current_module);

	PyObject *prev_module = first_module;
	for(size_t i = 1; i < appendix->context_length; ++i) {
		PyObject *elem = PyDict_New();
		PyObject *cur = PyObject_GetAttr(appendix->contexts[0], pystring_thread);
		PyDict_SetItem(elem, pystring_thread, PyObject_CallFunctionObjArgs(thread_encoder, cur, NULL));
		PyObject *cur_module = PyObject_GetAttr(cur, pystring_module);
		Py_DECREF(cur);
		PyDict_SetItem(elem, pystring_relationship, cur_module == prev_module ? pystring_sibling : pystring_child);
		PyTuple_SET_ITEM(chain, i, elem);
		Py_DECREF(prev_module);
		prev_module = cur_module;
	}
	Py_DECREF(prev_module);

	return chain;
}

static PyObject*
Chain_iter(Chain *const self)
{
	assert(self);
	ChainIter *const iter = Chain_iter_from_to(self, 0, self->context_length);
	if(!iter) {
		assert(PyErr_Occurred());
		return NULL;
	}
	return (PyObject*)iter;
}

static ChainIter*
Chain_iter_from_to(Chain *const self, size_t from, size_t to)
{
	assert(self);
	ChainIter *const iter = (ChainIter*)ChainIterType.tp_alloc(&ChainIterType, 0);
	if(!iter) {
		assert(PyErr_Occurred());
		return NULL;
	}
	iter->chain = self;
	iter->from = from;
	iter->to = to;
	Py_INCREF(self);
	return iter;
}

static PyObject*
ChainIter_new(PyTypeObject *const type, PyObject *const args, PyObject *const kwds)
{
	assert(type);
	ChainIter *const self = (ChainIter*)type->tp_alloc(type, 0);
	if(!self) {
		return NULL;
	}

	self->chain = NULL;
	self->from = 0;
	self->to = 0;

	return (PyObject*)self;
}

static void
ChainIter_dealloc(ChainIter *const self)
{
	assert(self);
	assert(self->chain);
	Py_DECREF(self->chain);

	Py_TYPE(self)->tp_free((PyObject*)self);
}

static PyObject*
ChainIter_iter(ChainIter *const self)
{
	assert(self);
	Py_INCREF(self);
	return (PyObject*)self;
}

static PyObject*
ChainIter_next(ChainIter *const self)
{
	assert(self);
	assert(self->chain);
	if(self->from >= self->to) {
		//PyErr_SetNone(PyExc_StopIteration);
		return NULL;
	}
	PyObject *const obj = self->chain->contexts[self->from++];
	Py_INCREF(obj);
	return obj;
}

static PyModuleDef CModule = {
	PyModuleDef_HEAD_INIT,
	"C",
	"C extension types for schedsi.cpu.",
	-1,
	NULL, NULL, NULL, NULL, NULL
};

PyMODINIT_FUNC
PyInit_C(void)
{
	if(PyType_Ready(&ChainType) < 0 ||
		PyType_Ready(&ChainIterType) < 0 ||
		!(pystring_child = PyUnicode_InternFromString("child")) ||
		!(pystring_finish = PyUnicode_InternFromString("finish")) ||
		!(pystring_module = PyUnicode_InternFromString("module")) ||
		!(pystring_relationship = PyUnicode_InternFromString("relationship")) ||
		!(pystring_run_background = PyUnicode_InternFromString("run_background")) ||
		!(pystring_sibling = PyUnicode_InternFromString("sibling")) ||
		!(pystring_thread = PyUnicode_InternFromString("thread")) ||
		!(pystring_timeout = PyUnicode_InternFromString("timeout"))) {
		Py_XDECREF(pystring_child);
		Py_XDECREF(pystring_finish);
		Py_XDECREF(pystring_module);
		Py_XDECREF(pystring_relationship);
		Py_XDECREF(pystring_run_background);
		Py_XDECREF(pystring_sibling);
		Py_XDECREF(pystring_thread);
		Py_XDECREF(pystring_timeout);
		return NULL;
	}

	PyObject* module = PyModule_Create(&CModule);
	if(!module) {
		return NULL;
	}

	Py_INCREF(&ChainType);
	PyModule_AddObject(module, "Chain", (PyObject *)&ChainType);

	return module;
}
