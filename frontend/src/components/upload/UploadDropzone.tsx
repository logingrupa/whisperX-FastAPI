import { useDropzone } from 'react-dropzone';
import { toast } from 'sonner';
import { Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface UploadDropzoneProps {
  onFilesAdded: (files: File[]) => void;
  children: React.ReactNode;
  className?: string;
}

/**
 * Full-page drop target for audio/video file uploads
 *
 * Features:
 * - Accepts audio/* and video/* files with common extensions
 * - Shows overlay when dragging files over page
 * - Always-visible "Select files" button
 * - Toast notification for rejected files
 *
 * Pattern: noClick=true so clicking anywhere doesn't open picker
 * (button.onClick calls open() explicitly)
 */
export function UploadDropzone({
  onFilesAdded,
  children,
  className,
}: UploadDropzoneProps) {
  const {
    getRootProps,
    getInputProps,
    open,
    isDragActive,
  } = useDropzone({
    // Don't open file dialog on click - use button instead
    noClick: true,
    // Don't open on keyboard (we have explicit button)
    noKeyboard: true,
    // Accept audio and video files
    // Using both MIME wildcards AND extensions per RESEARCH.md Pitfall #1
    accept: {
      'audio/*': ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma'],
      'video/*': ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.m4v', '.wmv'],
    },
    onDrop: (acceptedFiles, fileRejections) => {
      // Handle rejected files with toast (RESEARCH.md Pitfall #2)
      if (fileRejections.length > 0) {
        const rejectedNames = fileRejections
          .map(rejection => rejection.file.name)
          .slice(0, 3);
        const moreCount = fileRejections.length > 3
          ? ` and ${fileRejections.length - 3} more`
          : '';

        toast.error('Invalid files rejected', {
          description: `${rejectedNames.join(', ')}${moreCount} - Only audio/video files are allowed`,
        });
      }

      // Add accepted files to queue
      if (acceptedFiles.length > 0) {
        onFilesAdded(acceptedFiles);
      }
    },
  });

  return (
    <div
      {...getRootProps()}
      className={cn('min-h-screen relative', className)}
    >
      <input {...getInputProps()} />

      {/* Drag overlay - shows when files are being dragged over */}
      {isDragActive && (
        <div className="fixed inset-0 bg-primary/10 backdrop-blur-sm z-50 flex flex-col items-center justify-center gap-4 pointer-events-none">
          <Upload className="h-16 w-16 text-primary animate-pulse" />
          <p className="text-2xl font-medium text-primary">
            Drop files here
          </p>
          <p className="text-muted-foreground">
            Audio and video files only
          </p>
        </div>
      )}

      {/* Page content with select button */}
      <div className="container mx-auto px-4 py-8">
        {/* Header with select button */}
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">Upload Files</h1>
          <Button onClick={open} size="lg">
            <Upload className="mr-2 h-5 w-5" />
            Select files
          </Button>
        </div>

        {/* Children (queue list, etc.) */}
        {children}

        {/* Empty state hint - only show if no children provided */}
        {!children && (
          <div className="border-2 border-dashed border-muted-foreground/25 rounded-lg p-12 text-center">
            <Upload className="mx-auto h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-lg text-muted-foreground mb-2">
              Drag and drop audio or video files here
            </p>
            <p className="text-sm text-muted-foreground/75">
              or click "Select files" above
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
