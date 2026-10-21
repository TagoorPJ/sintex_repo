import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { Template } from './model/types';
import { store, StoreError } from './store';

export const keys = {
  templates: ['templates'] as const,
  template: (id: string) => ['template', id] as const,
  festivals: ['festivals'] as const,
};

export function useTemplates() {
  return useQuery({ queryKey: keys.templates, queryFn: () => store.listTemplates() });
}

export function useTemplate(id: string | undefined) {
  return useQuery({
    queryKey: keys.template(id ?? 'new'),
    queryFn: () => store.getTemplate(id!),
    enabled: !!id,
    staleTime: Infinity, // editor owns the doc after the first load
    retry: (count, e) => !(e instanceof StoreError && e.status === 404) && count < 2,
  });
}

export function useFestivals() {
  return useQuery({ queryKey: keys.festivals, queryFn: () => store.listFestivals(), staleTime: 60_000 });
}

const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong.');

function useInvalidate() {
  const qc = useQueryClient();
  return (t?: Template) => {
    void qc.invalidateQueries({ queryKey: keys.templates });
    void qc.invalidateQueries({ queryKey: keys.festivals });
    if (t) qc.setQueryData(keys.template(t.id), t);
  };
}

export function useDuplicateTemplate() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => store.duplicateTemplate(id),
    onSuccess: (t) => invalidate(t),
    onError: (e) => toast.error(`Couldn't duplicate. ${message(e)}`),
  });
}

export function useSetActive() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (v: { id: string; active: boolean; replaceFestival?: boolean }) => store.setActive(v.id, v.active, { replaceFestival: v.replaceFestival }),
    onSuccess: (t) => invalidate(t),
  });
}

export function useDeleteTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (t: Template) => store.deleteTemplate(t.id),
    // optimistic, card disappears right away and comes back if the delete fails
    onMutate: async (t) => {
      await qc.cancelQueries({ queryKey: keys.templates });
      const previous = qc.getQueryData<Template[]>(keys.templates);
      qc.setQueryData<Template[]>(keys.templates, (list) => list?.filter((x) => x.id !== t.id));
      return { previous };
    },
    onError: (e, t, ctx) => {
      if (ctx?.previous) qc.setQueryData(keys.templates, ctx.previous);
      toast.error(`Couldn't delete “${t.name}”. ${message(e)}`);
    },
    onSuccess: (_d, t) => toast.success(`Deleted “${t.name}”.`),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.templates });
      void qc.invalidateQueries({ queryKey: keys.festivals });
    },
  });
}

export function useCreateFestival() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { label: string; aliases: string[] }) => store.createFestival(input),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.festivals }),
  });
}
